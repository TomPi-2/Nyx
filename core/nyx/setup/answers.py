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

from rapidfuzz import fuzz

from nyx.index.aliases import normalize
from nyx.tools.nyx_control import COLORS, TINTS

Kind = Literal[
    "next", "back", "skip", "pick", "size", "mic", "speaker", "wake", "data", "done", "heard"
]

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
#: «Terminar», «terminad», «termina ya», «acabamos»…: por la raíz (whisper cambia la terminación).
_DONE = re.compile(r" (termin|acab)\w* | fin ")
#: Lo que dice que se habla de la salida (los altavoces), no del micrófono.
_OUTPUT = ("altavoz", "altavoces", "cascos", "auriculares", "salida", "suena", "sonar", "oigo")
#: Parecido letra a letra para aceptar un nombre mal oído («lavenda» → lavanda).
FUZZY_RATIO = 80


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
    """El nombre más largo que aparezca (azul cielo antes que azul) o, si no hay ninguno, el
    que más se parezca a lo oído: whisper parte o cambia las palabras raras («Pónteme la
    cotón» por «ponte melocotón», ERRORES.md 2026-11-14)."""
    for word in sorted(options, key=len, reverse=True):
        if f" {word} " in said:
            return options[word]
    return _near(said, options)


def _near(said: str, options: dict[str, str]) -> str | None:
    words = said.split()
    grams = ["".join(words[i : i + n]) for n in (1, 2, 3) for i in range(len(words) - n + 1)]
    best: tuple[float, str] | None = None
    for name, value in options.items():
        key = name.replace(" ", "")
        if len(key) < 5:  # «rosa», «azul», «lima»: demasiado cortas para adivinar
            continue
        for gram in grams:
            score = fuzz.ratio(key, gram)
            # El final de un nombre largo («cotón» de melocotón): whisper se come el principio.
            if len(gram) >= 5 and 2 * len(gram) >= len(key) and key.endswith(gram):
                score = max(score, 90.0)
            if score >= FUZZY_RATIO and (best is None or score > best[0]):
                best = (score, value)
    return best[1] if best else None


#: Más pequeña en cualquier forma: pequeña, pequeño, pequeñita, chica, chiquito, menos…
_SMALLER = re.compile(r" (pequen\w*|chic\w*|chiqu\w*|diminut\w*|encog\w*|menos|reduc\w*) ")
_BIGGER = re.compile(r" (grande\w*|agrand\w*|crece\w*|enorme|mas) ")
_A_LOT = re.compile(r" (mucho|bastante|muchisimo) ")


def _size(said: str, current: int) -> int | None:
    if number := re.search(r"\d+", said):
        value = int(number.group())
    elif _has(said, ("normal", "de siempre", "como antes", "por defecto")):
        value = SIZE_DEFAULT
    elif smaller := _SMALLER.search(said):
        # Antes que «más»: «más pequeña» y «más pequeño» (este hacía a Nyx más grande,
        # ERRORES.md 2026-11-14).
        steps = 4 if _A_LOT.search(said[: smaller.start() + 1]) else 2
        value = current - steps * SIZE_STEP
    elif bigger := _BIGGER.search(said):
        steps = 4 if _A_LOT.search(said[: bigger.start() + 1]) or " enorme " in said else 2
        value = current + steps * SIZE_STEP
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
    speakers: Sequence[str] = (),
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
        # «Suena por los cascos» es la salida; si no se dice, el micrófono (mismos nombres a
        # veces: «Realtek» está en los dos).
        if _has(said, _OUTPUT) and (i := _device(said, speakers)) is not None:
            return Answer("speaker", i)
        if (i := _device(said, mics)) is not None:
            return Answer("mic", i)
    if step == "data":
        if _has(said, _NO):
            return Answer("data", False)
        if not data_chosen and _has(said, _YES):
            return Answer("data", True)
        if data_chosen and (_has(said, _NEXT) or _DONE.search(said)):
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


def _device(said: str, names: Sequence[str]) -> int | None:
    for i, name in enumerate(names):
        words = [w for w in normalize(name).split() if len(w) > 3 and not w.isdigit()]
        if any(f" {w} " in said for w in words):
            return i
    return None


#: Lo que se puede contestar en cualquier paso (para la pista a whisper).
_COMMON = "Siguiente. Atrás. Vale. Terminar."
_COLOR_WORDS = (
    "Blanco, perla, arena, melocotón, coral, rojo, rosa, fucsia, lavanda, violeta, azul cielo, "
    "azul, turquesa, menta, verde, lima, amarillo, ámbar, grafito."
)
_TINT_WORDS = (
    "Gris, grafito, azul noche, océano, bosque, salvia, ciruela, vino, rosa, arena, cobre, lavanda."
)


def vocabulary(step: str) -> str:
    """Las palabras que se esperan en `step`, como pista a whisper (prompt): con ellas oye
    «melocotón» en vez de «la cotón»."""
    words = {
        "welcome": "Empezar. Saltar.",
        "mic": "Nyx.",
        "color": _COLOR_WORDS,
        "tint": _TINT_WORDS,
        "size": "Más grande, más pequeña, más pequeño, normal.",
        "data": "Sí, ayudo. No, gracias.",
    }.get(step, "")
    return f"Nyx. {words} {_COMMON}".replace("Nyx. Nyx.", "Nyx.").strip()
