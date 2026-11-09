"""Respuesta informativa del LLM: {display, secondary, spoken} (SPEC secciones 5 y 6).

Ollama genera el JSON con una gramática que sigue el esquema y en el orden de sus campos.
`spoken` va primero: el lector incremental lo entrega a trozos y la voz empieza con la
primera frase (medido: ~250 ms antes que con la burbuja delante). `display` y `secondary`
llegan después, mientras Nyx ya habla, y la burbuja aparece en cuanto están completos.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

from pydantic import BaseModel

REPLY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "spoken": {"type": "string"},
        "display": {"type": "string"},
        "secondary": {"type": "string"},
    },
    "required": ["spoken", "display", "secondary"],
}


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
    """`spoken` está completo: lo que quede en el divisor de frases ya se puede decir."""


ReplyEvent = BubbleReady | SpokenDelta | SpokenEnd


class _S(Enum):
    START = auto()  # antes de «{»
    KEY_OR_END = auto()
    KEY = auto()
    COLON = auto()
    VALUE = auto()  # antes de la comilla del valor
    STRING = auto()
    ESCAPE = auto()
    UNICODE = auto()
    AFTER_VALUE = auto()
    DONE = auto()


_ESCAPES = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}


class ReplyStreamParser:
    """Lector de un objeto JSON plano de cadenas, carácter a carácter."""

    STREAMED = "spoken"

    def __init__(self) -> None:
        self._state = _S.START
        self._key = ""
        self._buf: list[str] = []
        self._in_key = False
        self._hex = ""
        self._high_surrogate: int | None = None
        self._fields: dict[str, str] = {}
        self._bubble_sent: tuple[str, str] | None = None
        self._spoken_closed = False
        self.raw: list[str] = []

    @property
    def fields(self) -> dict[str, str]:
        return dict(self._fields)

    def feed(self, chunk: str) -> list[ReplyEvent]:
        self.raw.append(chunk)
        events: list[ReplyEvent] = []
        delta: list[str] = []
        self._spoken_closed = False
        for ch in chunk:
            self._step(ch, delta, events)
        if delta:
            events.append(SpokenDelta("".join(delta)))
        if self._spoken_closed:
            events.append(SpokenEnd())
        return events

    def finish(self) -> Reply:
        # JSON cortado (timeout o cancelación): se usa lo que haya llegado.
        if self._state in (_S.STRING, _S.ESCAPE, _S.UNICODE) and not self._in_key:
            self._fields[self._key] = "".join(self._buf)
        return Reply(**{k: v for k, v in self._fields.items() if k in Reply.model_fields})

    # --- máquina de estados ---

    def _bubble_event(self, events: list[ReplyEvent]) -> None:
        bubble = (self._fields.get("display", ""), self._fields.get("secondary", ""))
        if bubble != self._bubble_sent and (bubble[0] or bubble[1]):
            self._bubble_sent = bubble
            events.append(BubbleReady(*bubble))

    def _emit_char(self, ch: str, delta: list[str]) -> None:
        self._buf.append(ch)
        if not self._in_key and self._key == self.STREAMED:
            delta.append(ch)

    def _step(self, ch: str, delta: list[str], events: list[ReplyEvent]) -> None:
        s = self._state
        if s is _S.START:
            if ch == "{":
                self._state = _S.KEY_OR_END
        elif s is _S.KEY_OR_END:
            if ch == '"':
                self._buf, self._in_key, self._state = [], True, _S.STRING
            elif ch == "}":
                self._state = _S.DONE
        elif s is _S.COLON:
            if ch == ":":
                self._state = _S.VALUE
        elif s is _S.VALUE:
            if ch == '"':
                self._buf, self._in_key, self._state = [], False, _S.STRING
                if self._key == self.STREAMED:
                    # Si el modelo empieza a hablar antes de rellenar la burbuja, se muestra
                    # lo que haya; si luego llega más, se actualiza.
                    self._bubble_event(events)
        elif s is _S.STRING:
            if ch == "\\":
                self._state = _S.ESCAPE
            elif ch == '"':
                text = "".join(self._buf)
                if self._in_key:
                    self._key, self._state = text, _S.COLON
                else:
                    self._fields[self._key] = text
                    self._state = _S.AFTER_VALUE
                    if self._key == self.STREAMED:
                        self._spoken_closed = True
                    # La burbuja sale cuando tiene sus dos campos (o se actualiza si ya salió).
                    complete = "display" in self._fields and "secondary" in self._fields
                    if self._key in ("display", "secondary") and (
                        complete or self._bubble_sent is not None
                    ):
                        self._bubble_event(events)
            else:
                self._emit_char(ch, delta)
        elif s is _S.ESCAPE:
            if ch == "u":
                self._hex, self._state = "", _S.UNICODE
            else:
                self._emit_char(_ESCAPES.get(ch, ch), delta)
                self._state = _S.STRING
        elif s is _S.UNICODE:
            self._hex += ch
            if len(self._hex) == 4:
                self._state = _S.STRING
                self._unicode(int(self._hex, 16), delta)
        elif s is _S.AFTER_VALUE:
            if ch == ",":
                self._state = _S.KEY_OR_END
            elif ch == "}":
                self._state = _S.DONE

    def _unicode(self, code: int, delta: list[str]) -> None:
        if 0xD800 <= code <= 0xDBFF:
            self._high_surrogate = code
            return
        if 0xDC00 <= code <= 0xDFFF and self._high_surrogate is not None:
            code = 0x10000 + ((self._high_surrogate - 0xD800) << 10) + (code - 0xDC00)
        self._high_surrogate = None
        self._emit_char(chr(code), delta)
