"""Respuestas informativas del LLM en texto a trozos (SPEC secciones 5 y 6).

Formato que se pide al modelo:

    [Hallo | hola · alemán]
    En alemán se dice Hallo.

La primera línea, entre corchetes, es la burbuja (dato destacado | línea secundaria); el resto
es lo que se dice en voz alta y se entrega a trozos para empezar a hablar enseguida. (No se
usa un JSON con esquema porque Ollama no permite combinarlo con las herramientas.)
Si el modelo se salta la cabecera, todo es voz y la burbuja se saca de la primera frase. Si
olvida el «]», la cabecera acaba en el salto de línea; si solo escribe la cabecera, se dice el
dato.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import BaseModel

MAX_HEADER = 160  # si no se cierra el corchete en esto, no era una cabecera
_MARKDOWN = re.compile(r"[*_`#]+")


class Reply(BaseModel):
    display: str = ""
    secondary: str = ""
    spoken: str = ""


@dataclass(frozen=True, slots=True)
class BubbleReady:
    display: str
    secondary: str


@dataclass(frozen=True, slots=True)
class SpokenDelta:
    text: str


@dataclass(frozen=True, slots=True)
class SpokenEnd:
    """La respuesta hablada está completa: lo que quede en el divisor de frases se dice ya."""


ReplyEvent = BubbleReady | SpokenDelta | SpokenEnd


def parse_header(header: str) -> BubbleReady:
    inner = header.strip().strip("[]").strip()
    display, _, secondary = inner.partition("|")
    display, secondary = display.strip(), secondary.strip()
    if secondary and _same(display, secondary):
        # «[10 archivos en Descargas | hay 10 archivos en Descargas]»: una vez basta (en la
        # burbuja y en la voz).
        secondary = ""
    return BubbleReady(display, secondary)


def _same(a: str, b: str) -> bool:
    """¿Dicen lo mismo? (una contiene a la otra o casi iguales, sin mayúsculas ni signos)"""
    from rapidfuzz import fuzz

    na, nb = (" ".join(re.sub(r"[^\w\s]", " ", s.lower()).split()) for s in (a, b))
    if not na or not nb:
        return False
    return na in nb or nb in na or fuzz.token_set_ratio(na, nb) >= 85


def clean(text: str) -> str:
    """Fuera markdown: la voz leería los asteriscos."""
    return _MARKDOWN.sub("", text)


def _looks_like_sentence(text: str) -> bool:
    return text.endswith((".", "!", "?")) or len(text.split()) >= 5


class TextReplyParser:
    def __init__(self) -> None:
        self._pending = ""  # texto aún sin clasificar (¿cabecera o voz?)
        self._header_done = False
        self.bubble: BubbleReady | None = None
        self.spoken: list[str] = []

    def feed(self, chunk: str) -> list[ReplyEvent]:
        events: list[ReplyEvent] = []
        if self._header_done:
            self._speak(chunk, events)
            return events
        self._pending += chunk
        start = self._pending.lstrip()
        if not start:
            return events
        if not start.startswith("["):
            self._header_done = True
            text, self._pending = self._pending, ""
            self._speak(text, events)
            return events
        ends = [i for i in (start.find("]"), start.find("\n")) if i >= 0]
        end = min(ends) if ends else -1
        if end < 0:
            if len(start) > MAX_HEADER:  # no era una cabecera
                self._header_done = True
                text, self._pending = self._pending, ""
                self._speak(text, events)
            return events
        header = parse_header(start[: end + 1])
        self._header_done = True
        if header.display:  # «[» suelto con salto de línea: no hay cabecera
            self.bubble = header
            events.append(header)
        rest, self._pending = start[end + 1 :], ""
        self._speak(rest, events)
        return events

    def _speak(self, text: str, events: list[ReplyEvent]) -> None:
        if not self.spoken:
            text = text.lstrip()  # el salto de línea tras la cabecera
        text = clean(text)
        if text:
            self.spoken.append(text)
            events.append(SpokenDelta(text))

    def finish(self) -> tuple[list[ReplyEvent], Reply]:
        events: list[ReplyEvent] = []
        if self._pending:  # una cabecera corta sin cerrar ni texto detrás
            self.bubble = parse_header(self._pending)
            events.append(self.bubble)
            self._pending = ""
        if not self.spoken and self.bubble is not None:
            # Solo cabecera: se dice el dato y su contexto («agujero negro, un objeto…»). Si el
            # contexto ya es una frase entera («El uso de CPU está al 30 %.»), se dice sin repetir
            # la etiqueta de delante.
            said = self.bubble.display
            if self.bubble.secondary:
                sec = self.bubble.secondary.strip()
                said = sec if _looks_like_sentence(sec) else f"{said}, {sec.replace(' · ', ', ')}"
            self._speak(said, events)
        events.append(SpokenEnd())
        spoken = "".join(self.spoken).strip()
        bubble = self.bubble or BubbleReady(first_sentence(spoken), "")
        return events, Reply(display=bubble.display, secondary=bubble.secondary, spoken=spoken)


def first_sentence(text: str, limit: int = 60) -> str:
    m = re.match(r"(.+?[.!?])(\s|$)", text)
    sentence = m.group(1) if m else text
    return sentence if len(sentence) <= limit else sentence[: limit - 1].rstrip() + "…"
