"""Brain: arma el prompt, llama al LLM con las herramientas y traduce lo que devuelve:

- Una pregunta → texto a trozos para la voz y la burbuja (ReplyEvent… y ReplyDone).
- Una acción → ToolPlan con las llamadas a herramientas, en orden (las ejecuta el pipeline).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncGenerator, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from nyx.brain.base import ChatMessage, LLMEngine, LLMError, LLMToolCall
from nyx.brain.memory import ShortMemory
from nyx.brain.panel import unrelated
from nyx.brain.prompts import (
    ADDRESSED_SCHEMA,
    TOOLS_HINT,
    addressed_messages,
    system_message,
    user_message,
)
from nyx.brain.reply import MAX_HEADER, Reply, ReplyEvent, TextReplyParser, first_sentence
from nyx.brain.select import ToolSelector
from nyx.brain.textcalls import could_be_call, parse_text_calls
from nyx.settings.model import ResponseTone

log = logging.getLogger(__name__)

# Principio de una respuesta aún sin decidir: nombre (posible herramienta) sin terminar.
_UNDECIDED = re.compile(r"^\s*`*\s*[A-Za-z_]*\s*$")

# Orden escrita como texto (6.21): sin cabecera «[…]», corta y en una línea. El 7B a veces
# contesta «pon el volumen al 100» en vez de llamar a la herramienta; si el router la entiende,
# se ejecuta. Más larga o con más de una frase, es una respuesta normal.
MAX_COMMAND_WORDS = 8
_MORE_THAN_ONE_LINE = re.compile(r"[.!?]\s+\S|\n\s*\S")

# Grupos sin aviso: hablar de Nyx o pedirle cosas suyas no es consultar el estado del PC, y
# «¿qué puedes hacer?» se contestaba bien sin él.
HINTLESS_GROUPS = frozenset({"nyx"})

#: De una orden escrita a las llamadas que haría el router (None si no la entiende).
Reroute = Callable[[str], list[LLMToolCall] | None]


def _still_a_command(text: str) -> bool:
    """¿Puede seguir siendo una orden escrita? (falso en cuanto es claramente una respuesta)"""
    return len(text.split()) <= MAX_COMMAND_WORDS and not _MORE_THAN_ONE_LINE.search(text)


def _after_header(text: str) -> str | None:
    """El texto tras la cabecera «[…]» si la hay; None si la cabecera aún no ha terminado."""
    start = text.lstrip()
    if not start.startswith("["):
        return text
    ends = [i for i in (start.find("]"), start.find("\n")) if i >= 0]
    if not ends:
        return None if len(start) <= MAX_HEADER else text
    return start[min(ends) + 1 :]


@dataclass(frozen=True, slots=True)
class ReplyDone:
    reply: Reply


@dataclass(frozen=True, slots=True)
class ToolPlan:
    calls: list[LLMToolCall]


def worth_remembering(reply: Reply) -> bool:
    """Las respuestas raras («pausa», «aún no sé hacer eso») no se guardan: con ellas en la
    memoria corta, el modelo las imita en las preguntas siguientes (pasó en la fase 5)."""
    from nyx.index.aliases import normalize

    spoken = normalize(reply.spoken)
    if not spoken or spoken.startswith(("aun no se", "aun no puedo")):
        return False
    return len(spoken.split()) >= 4 or reply.spoken.rstrip().endswith((".", "?", "!"))


class Brain:
    def __init__(
        self,
        llm: LLMEngine,
        memory: ShortMemory | None = None,
        clock: Callable[[], datetime] = datetime.now,
        tools: Sequence[dict[str, Any]] = (),
        *,
        tone: ResponseTone = "cercano",
        selector: ToolSelector | None = None,
        reroute: Reroute | None = None,
        tools_hint: bool = False,
    ) -> None:
        self.llm = llm
        self.memory = memory or ShortMemory()
        self._clock = clock
        self.tools = list(tools)
        # Con selector (6.20b), cada petición ve las fijas y los grupos de su tema; sin él,
        # siempre `tools` (pruebas y comparaciones: `battery.py --sin-grupos`).
        self.selector = selector
        self.reroute = reroute
        # Avisar al modelo de que la petición se resuelve con herramientas (6.21). Medido con
        # qwen2.5:7b: no le hace consultar más (259 frente a 262/337); queda para otros modelos.
        self.tools_hint = tools_hint
        # Se elige al arrancar para no romper la caché del prefijo de Ollama (6.15).
        self._system = system_message(tone)

    def tools_for(self, text: str, *, keep: bool = False) -> list[dict[str, Any]]:
        if self.selector is None:
            return self.tools
        return self.selector.select(text, keep=keep)

    def _needs_tools(self, text: str) -> bool:
        """¿La frase toca un tema que solo saben o hacen las herramientas?"""
        if self.selector is None:
            return False
        return bool(set(self.selector.groups_for(text)) - HINTLESS_GROUPS)

    async def warmup(self) -> None:
        # Con selector, el prefijo de arranque son las fijas (y los grupos vigentes, si hay).
        await self.llm.warmup([self._system], tools=self.tools_for(""))

    def build_messages(self, text: str, extra: str = "") -> list[ChatMessage]:
        if action := self.memory.action():
            # Probado con el 7B: así entiende «ábrela», «muévela», «bórrala» (10/10), y como
            # turno de la conversación no (tarea 6.02).
            last = (
                "Lo último que has hecho, por si el usuario se refiere a ello con «la», «lo», "
                f"«eso»…: {action}."
            )
            extra = f"{last} {extra}" if extra else last
        return [
            self._system,
            *self.memory.messages(),
            user_message(text, self._clock(), extra),
        ]

    async def respond(
        self,
        text: str,
        extra: str = "",
        *,
        continuing: bool = False,
        tools_off: bool = False,
    ) -> AsyncGenerator[ReplyEvent | ReplyDone | ToolPlan, None]:
        """`extra`: contexto de esta petición (ventana activa, candidatos si no se encontró…).

        `continuing`: es otra vuelta de la misma petición (bucle de agente): el turno de la
        memoria corta se sustituye en vez de añadir otro.

        `tools_off`: sin herramientas (tras leer una web, 6.06: lo que diga no puede hacer que
        Nyx actúe; solo se cuenta)."""
        parser = TextReplyParser()
        calls: list[LLMToolCall] = []
        tools = [] if tools_off else self.tools_for(text, keep=continuing)
        if not continuing and self.tools_hint and self._needs_tools(text):
            extra = f"{extra}\n{TOOLS_HINT}" if extra else TOOLS_HINT
        # Una llamada escrita como texto a una herramienta que no estaba en la lista también
        # cuenta: existe y se ejecuta (el selector puede haberse quedado corto).
        names = (
            sorted(self.selector.names)
            if self.selector is not None
            else [t["function"]["name"] for t in tools]
        )
        held = ""  # principio retenido: ¿texto o una llamada escrita como texto?
        mode = "?" if tools else "text"
        # Nunca en otra vuelta del bucle de agente: ahí el modelo acaba de leer contenido de
        # fuera (portapapeles, webs), que no puede convertirse en órdenes.
        reroute = self.reroute if not continuing else None
        async for piece in self.llm.chat(self.build_messages(text, extra), tools=tools):
            if isinstance(piece, list):
                calls += piece
                continue
            if calls:  # si decide actuar, el texto que acompañe no se dice
                continue
            if mode == "?":
                held += piece
                # Lo que va tras una cabecera «[…]» también puede ser una llamada escrita
                # («[acciones]\nset_timer({…})»).
                body = _after_header(held)
                if body is None or _UNDECIDED.match(body):
                    continue
                if could_be_call(body, names):
                    mode, piece = "call", ""
                elif reroute is not None and not held.lstrip().startswith("["):
                    mode, piece = "command?", ""  # sin cabecera: ¿una orden escrita?
                else:
                    mode, piece, held = "text", held, ""
            if mode == "call":
                held += piece
                continue
            if mode == "command?":
                held += piece
                if _still_a_command(held):
                    continue
                mode, piece, held = "text", held, ""
            for event in parser.feed(piece):
                yield event
        if not calls and held:
            calls = parse_text_calls(_after_header(held) or held, names)
            if calls:
                log.info("Llamadas escritas como texto: %r", held[:200])
            elif (
                reroute is not None
                and not held.lstrip().startswith("[")
                and _still_a_command(held)
                and (calls := reroute(held.strip().rstrip(".!")) or [])
            ):
                log.info("Orden escrita como texto, al router: %r → %s", held, calls)
            else:  # no lo era: se trata como respuesta normal
                for event in parser.feed(held):
                    yield event
        if calls:
            # La memoria se escribe tras ejecutar, con lo que pasó (Pipeline → remember).
            yield ToolPlan(calls)
            return
        tail, reply = parser.finish()
        for event in tail:
            yield event
        if not reply.spoken:
            log.warning("Respuesta vacía del LLM para %r", text)
        if worth_remembering(reply):
            display, secondary = reply.display, reply.secondary
            if unrelated(display, secondary, reply.spoken, text):
                # Una cabecera sin relación («[Noche]») no se guarda: el modelo la copiaría en
                # todas las respuestas siguientes (ERRORES.md, 2026-11-14).
                display, secondary = first_sentence(reply.spoken.strip()), ""
            self.memory.add(text, f"[{display} | {secondary}]\n{reply.spoken}", replace=continuing)
        else:
            log.info("Respuesta que no se guarda en la memoria: %r", reply.spoken)
        yield ReplyDone(reply)

    def remember_action(self, note: str) -> None:
        """Lo último que hizo Nyx (lo escribe el Pipeline tras ejecutar, con lo que pasó de
        verdad; ver brain/agent.py, memory_note)."""
        self.memory.set_action(note)

    async def addressed(self, text: str) -> bool:
        """¿Va dirigida a Nyx una frase oída en la ventana de seguimiento (sin decir «Nyx»)?

        Una llamada aparte, corta y con ejemplos: el modelo de 7B clasifica bien así (14/15
        en las pruebas, ~250 ms), mientras que ignora la instrucción si va dentro del prompt
        normal. Si falla, se da por dirigida: el error normal del LLM lo explicará.
        """
        raw = ""
        try:
            messages = addressed_messages(text, self.memory.last_turn())
            async for chunk in self.llm.stream(messages, schema=ADDRESSED_SCHEMA):
                raw += chunk
            return bool(json.loads(raw)["para_nyx"])
        except (LLMError, ValueError, KeyError, TypeError):
            log.warning("No se pudo clasificar el seguimiento %r: %r", text, raw[:80])
            return True
