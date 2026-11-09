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
from nyx.brain.prompts import (
    ADDRESSED_SCHEMA,
    addressed_messages,
    system_message,
    user_message,
)
from nyx.brain.reply import Reply, ReplyEvent, TextReplyParser
from nyx.brain.textcalls import could_be_call, parse_text_calls

log = logging.getLogger(__name__)

# Principio de una respuesta aún sin decidir: nombre (posible herramienta) sin terminar.
_UNDECIDED = re.compile(r"^\s*`*\s*[A-Za-z_]*\s*$")


@dataclass(frozen=True, slots=True)
class ReplyDone:
    reply: Reply


@dataclass(frozen=True, slots=True)
class ToolPlan:
    calls: list[LLMToolCall]


def describe_plan(calls: Sequence[LLMToolCall]) -> str:
    """Lo que se guarda en la memoria corta: «y ahora ciérralo» necesita saber qué se abrió."""
    parts = [f"{c.name}({json.dumps(c.arguments, ensure_ascii=False)})" for c in calls]
    return "[acciones] " + "; ".join(parts)


class Brain:
    def __init__(
        self,
        llm: LLMEngine,
        memory: ShortMemory | None = None,
        clock: Callable[[], datetime] = datetime.now,
        tools: Sequence[dict[str, Any]] = (),
    ) -> None:
        self.llm = llm
        self.memory = memory or ShortMemory()
        self._clock = clock
        self.tools = list(tools)

    async def warmup(self) -> None:
        await self.llm.warmup([system_message()], tools=self.tools)

    def build_messages(self, text: str, extra: str = "") -> list[ChatMessage]:
        return [
            system_message(),
            *self.memory.messages(),
            user_message(text, self._clock(), extra),
        ]

    async def respond(
        self, text: str, extra: str = ""
    ) -> AsyncGenerator[ReplyEvent | ReplyDone | ToolPlan, None]:
        """`extra`: contexto de esta petición (ventana activa, candidatos si no se encontró…)."""
        parser = TextReplyParser()
        calls: list[LLMToolCall] = []
        names = [t["function"]["name"] for t in self.tools]
        held = ""  # principio retenido: ¿texto o una llamada escrita como texto?
        mode = "?" if names else "text"
        async for piece in self.llm.chat(self.build_messages(text, extra), tools=self.tools):
            if isinstance(piece, list):
                calls += piece
                continue
            if calls:  # si decide actuar, el texto que acompañe no se dice
                continue
            if mode == "?":
                held += piece
                if _UNDECIDED.match(held):
                    continue
                mode = "call" if could_be_call(held, names) else "text"
                piece, held = (held, "") if mode == "text" else ("", held)
            if mode == "call":
                held += piece
                continue
            for event in parser.feed(piece):
                yield event
        if not calls and held:
            calls = parse_text_calls(held, names)
            if calls:
                log.info("Llamadas escritas como texto: %r", held[:200])
            else:  # no lo era: se trata como respuesta normal
                for event in parser.feed(held):
                    yield event
        if calls:
            self.memory.add(text, describe_plan(calls))
            yield ToolPlan(calls)
            return
        tail, reply = parser.finish()
        for event in tail:
            yield event
        if not reply.spoken:
            log.warning("Respuesta vacía del LLM para %r", text)
        self.memory.add(text, f"[{reply.display} | {reply.secondary}]\n{reply.spoken}")
        yield ReplyDone(reply)

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
