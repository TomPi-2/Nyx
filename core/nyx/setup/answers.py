"""Entender lo que el usuario contesta en el primer arranque guiado (tarea 9.10).

Sin el cerebro (en el primer arranque aún se está descargando): reglas cerradas para cada
paso. Lo usa también la 9.11 («Nyx, quiero cambiarte el color» saca el mismo panel).

    understand("color", "ponte azul cielo")  → Answer("pick", "azul_cielo")
    understand("size", "un poco más grande", size=100) → Answer("size", 120)
    understand("data", "no, gracias")        → Answer("data", False)
    understand("mic", "siguiente")           → Answer("next")
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from nyx.index.aliases import normalize
from nyx.tools.nyx_control import COLORS, TINTS

Kind = Literal["next", "back", "skip", "pick", "size", "mic", "wake", "data", "done", "heard"]

SIZE_MIN, SIZE_MAX, SIZE_STEP, SIZE_DEFAULT = 60, 180, 10, 100

_NEXT: tuple[str, ...] = (
    "siguiente", "vale", "listo", "lista", "empezar", "empieza", "empezamos", "adelante",
    "sigue", "seguimos", "continua", "continuar", "venga", "ok", "okay", "perfecto",
)  # fmt: skip
_BACK = ("atras", "anterior", "vuelve", "volver")
_SKIP = ("saltar", "salta", "saltalo", "luego", "despues", "ahora no")
_YES = ("si", "claro", "vale", "bueno", "acepto", "ayudo")
_NO = ("no", "nunca", "paso")
_WAKE = ("nyx", "nix", "nics", "nicks")


@dataclass(frozen=True, slots=True)
class Answer:
    kind: Kind
    value: str | int | bool | None = None


def _words(text: str) -> str:
    """El texto normalizado entre espacios, para buscar palabras enteras."""
    return f" {normalize(text)} "


def _has(said: str, options: Sequence[str]) -> bool:
    return any(f" {o} " in said for o in options)


def _name(said: str, options: dict[str, str]) -> str | None:
    """El nombre más largo que aparezca (azul cielo antes que azul)."""
    for word in sorted(options, key=len, reverse=True):
        if f" {word} " in said:
            return options[word]
    return None


def _size(said: str, current: int) -> int | None:
    if number := re.search(r"\d+", said):
        value = int(number.group())
    elif _has(said, ("normal", "de siempre", "como antes", "por defecto")):
        value = SIZE_DEFAULT
    elif _has(said, ("mucho mas grande", "bastante mas grande", "enorme")):
        value = current + 4 * SIZE_STEP
    elif _has(said, ("mucho mas pequena", "bastante mas pequena", "diminuta")):
        value = current - 4 * SIZE_STEP
    elif _has(said, ("pequena", "chica", "encogete", "menos", "reduce")):
        value = current - 2 * SIZE_STEP  # antes que «más»: «más pequeña»
    elif _has(said, ("grande", "agrandate", "crece", "mas")):
        value = current + 2 * SIZE_STEP
    else:
        return None
    value = round(value / SIZE_STEP) * SIZE_STEP
    return max(SIZE_MIN, min(SIZE_MAX, value))


def understand(
    step: str,
    text: str,
    *,
    size: int = SIZE_DEFAULT,
    mics: Sequence[str] = (),
    data_chosen: bool = False,
) -> Answer | None:
    """Lo que pide `text` en el paso `step`, o None si no se entiende."""
    said = _words(text)
    if not said.strip():
        return None
    # Lo propio de cada paso va antes que «siguiente» («vale, el azul» elige el azul).
    if step == "color" and (color := _name(said, COLORS)):
        return Answer("pick", color)
    if step == "tint" and (tint := _name(said, TINTS)):
        return Answer("pick", tint)
    if step == "size" and (value := _size(said, size)) is not None:
        return Answer("size", value)
    if step == "mic":
        if _has(said, _WAKE):
            return Answer("wake")
        for i, name in enumerate(mics):
            words = [w for w in normalize(name).split() if len(w) > 3]
            if any(f" {w} " in said for w in words):
                return Answer("mic", i)
    if step == "data":
        if _has(said, _NO):
            return Answer("data", False)
        if not data_chosen and _has(said, _YES):
            return Answer("data", True)
        if data_chosen and _has(said, (*_NEXT, "terminar", "termina", "acabar", "fin")):
            return Answer("done")
    if step == "welcome" and _has(said, _SKIP):
        return Answer("skip")
    if _has(said, _BACK):
        return Answer("back")
    if _has(said, _NEXT):
        return Answer("next")
    if step == "mic":
        return Answer("heard")  # cualquier otra cosa: la prueba de que se le oye
    return None
