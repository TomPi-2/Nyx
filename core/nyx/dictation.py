"""Dictado (tarea 8.04): «escribe lo que te diga».

Mientras está activo, Nyx escucha seguido (sin decir «Nyx», como en el primer arranque) y
escribe lo que oye en la ventana en la que estabas, hasta «ya está» o 20 s sin hablar. La
puntuación se puede decir («coma», «punto», «nueva línea», «abre interrogación»…). Nunca pulsa
Intro a secas (en un chat enviaría el mensaje): una línea nueva es Mayús+Intro. Nunca en
juegos ni en terminales (eso lo comprueba la herramienta `dictation`).
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass

from nyx.index.aliases import normalize

log = logging.getLogger(__name__)

#: Sin hablar este tiempo, el dictado termina solo.
SILENCE_S = 20.0
FOCUS_SETTLE_S = 0.15

STOP = re.compile(
    r"^(?:(?:vale|bueno|ok)\s+)?(?:ya\s+esta|ya\s+he\s+terminado|ya|fin\s+del\s+dictado|"
    r"(?:para|deja)\s+de\s+(?:escribir|dictar)|termina(?:r)?\s+(?:el\s+)?dictado|"
    r"eso\s+es\s+todo|nada\s+mas|stop)$"
)
# Palabras de puntuación dichas (lo que whisper escribe al oírlas), en orden: lo largo primero.
_SPOKEN = [
    (r"punto\s+y\s+aparte|nuevo\s+parrafo", ".\n\n"),
    (r"nueva\s+linea|salto\s+de\s+linea|punto\s+y\s+seguido\s+en\s+otra\s+linea", "\n"),
    (r"punto\s+y\s+coma", ";"),
    (r"dos\s+puntos", ":"),
    (r"puntos\s+suspensivos", "…"),
    (r"punto\s+y\s+seguido|punto(?:\s+final)?", "."),
    (r"coma", ","),
    (r"abre\s+interrogacion", "¿"),
    (r"cierra\s+interrogacion", "?"),
    (r"abre\s+exclamacion", "¡"),
    (r"cierra\s+exclamacion", "!"),
    (r"abre\s+parentesis", "("),
    (r"cierra\s+parentesis", ")"),
    (r"abre\s+comillas", "«"),
    (r"cierra\s+comillas", "»"),
    (r"guion", "-"),
]
_WAKE = re.compile(r"^\s*(?:nyx|nix|niks|nics)\s*[,.:!]?\s*", re.I)


def _pattern(words: str) -> re.Pattern[str]:
    # Sobre el texto original: con o sin tildes y con la puntuación que ponga whisper alrededor.
    loose = words.replace("i", "[iíÍI]").replace("a", "[aáAÁ]").replace("o", "[oóOÓ]")
    loose = loose.replace("e", "[eéEÉ]").replace("u", "[uúUÚ]")
    return re.compile(rf"[\s,.;:]*\b(?:{loose})\b[,.;:]?", re.I)


_RULES = [(_pattern(words), mark) for words, mark in _SPOKEN]


def spoken_text(raw: str) -> str:
    """«hola coma qué tal punto nueva línea adiós» → «hola, qué tal.\\nadiós»."""
    text = _WAKE.sub("", raw).strip()
    for pattern, mark in _RULES:
        text = pattern.sub(f"{mark} " if mark not in "¿¡(«" else f" {mark}", text)
    text = re.sub(r" +", " ", text)
    text = re.sub(r" ([,.;:?!)»…])", r"\1", text)
    text = re.sub(r"([¿¡(«]) ", r"\1", text)
    text = re.sub(r" *\n *", "\n", text)
    # Mayúscula tras punto, «?», «!» o línea nueva.
    text = re.sub(r"([.?!…]\s+|\n)([a-záéíóúñ])", lambda m: m.group(1) + m.group(2).upper(), text)
    return text.strip(" ")


def is_stop(text: str) -> bool:
    return bool(STOP.match(normalize(_WAKE.sub("", text)).strip(" .")))


@dataclass
class Target:
    hwnd: int
    title: str


class Dictation:
    """El estado del dictado: a qué ventana va y si sigue activo."""

    def __init__(
        self,
        *,
        write: Callable[[str], bool] | None = None,
        new_line: Callable[[], None] | None = None,
        focus: Callable[[int], bool] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._write = write or _write
        self._new_line = new_line or _new_line
        self._focus = focus or _focus
        self._clock = clock
        self.target: Target | None = None
        self.started = 0.0
        self.chunks = 0

    @property
    def active(self) -> bool:
        return self.target is not None

    def start(self, hwnd: int, title: str) -> None:
        self.target = Target(hwnd, title)
        self.started = self._clock()
        self.chunks = 0
        log.info("Dictado en «%s»", title)

    def stop(self) -> None:
        if self.target is not None:
            log.info("Fin del dictado (%d trozos)", self.chunks)
        self.target = None

    def type(self, raw: str) -> bool:
        """Escribe lo dicho en su ventana. False si ya no se puede (cerrada, otra app…)."""
        if self.target is None:
            return False
        text = spoken_text(raw)
        if not text:
            return True
        if not self._focus(self.target.hwnd):
            return False
        # Entre trozos, un espacio (salvo tras una línea nueva).
        if self.chunks and not text.startswith("\n"):
            text = " " + text
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if i:
                self._new_line()
            if line and not self._write(line):
                return False
        self.chunks += 1
        return True


def _focus(hwnd: int) -> bool:
    from nyx.winapi import windows

    fg = windows.foreground()
    if fg is not None and fg.hwnd == hwnd:
        return True
    if not windows.activate(hwnd):
        return False
    time.sleep(FOCUS_SETTLE_S)
    return True


def _write(text: str) -> bool:
    from nyx.winapi import keys

    return bool(keys.write(text))


def _new_line() -> None:
    from nyx.winapi import keys

    keys.press(keys.parse("shift+enter"))
