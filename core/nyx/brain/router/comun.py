"""Lo común a las reglas del router: Route, Miss, el registro de reglas (`rule`) y los
ayudantes que usan varios temas (números, horas, el texto original…)."""

from __future__ import annotations

import re
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from nyx.executor import ToolCall
from nyx.index.aliases import normalize
from nyx.index.model import Kind
from nyx.index.service import Match, SystemIndex
from nyx.stt.normalize import NUMBER_WORDS
from nyx.winapi import windows


@dataclass(frozen=True, slots=True)
class Route:
    calls: list[ToolCall]
    rule: str


@dataclass(frozen=True, slots=True)
class Miss:
    """El patrón encaja («abre X») pero X no se encuentra o es ambiguo."""

    target: str
    candidates: list[Match] = field(default_factory=list)
    # Suena casi como algo del equipo («epic gueims» → Epic Games): se le pregunta al usuario
    # «¿Abrir Epic Games?» y con un «sí» se hace (paso 2 de Cerebro 2).
    offer: Route | None = None
    offer_name: str = ""


_TENS = {"sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90, "cien": 100}


def parse_number(text: str) -> int | None:
    text = text.strip()
    if text.isdigit():
        return int(text)
    if text in _TENS:
        return _TENS[text]
    if text in NUMBER_WORDS:
        return NUMBER_WORDS[text]
    for word, tens in _TENS.items():
        if text.startswith(f"{word} y "):
            unit = NUMBER_WORDS.get(text.removeprefix(f"{word} y "))
            if unit is not None and 1 <= unit <= 9:
                return tens + unit
    return None


_NUM = r"(?P<n>\d{1,3}|[a-z]+(?: y [a-z]+)?)"
_POLITE = re.compile(r"\s+(?:por favor|porfa|gracias)$")
# Muletillas al empezar («vale, ábreme Netflix», «venga, pon música»; ERRORES.md, 2026-11-14).
# «Oye, …», «Eh… …», «Hey, …» (variantes de voz, 2026-11-15).
_LEAD = re.compile(
    r"^(?:(?:vale|venga|bueno|pues|a ver|ok|okey|por favor|porfa|oye|oiga|eh|ehm|em|mm|mmm|"
    r"hmm|hey|ey)\s+)+(?=\w)"
)
_THIS_WINDOW = {"", "esta ventana", "la ventana", "esto", "esta", "la ventana activa"}


def _clean(text: str) -> str:
    return _LEAD.sub("", _POLITE.sub("", normalize(text))).strip()


_RAW: ContextVar[str] = ContextVar("router_raw", default="")
_RAW_EXACT: ContextVar[str] = ContextVar("router_raw_exact", default="")

Handler = Callable[[re.Match[str], SystemIndex], "Route | Miss | None"]
# Cada tema registra aquí sus reglas; el orden en que se prueban lo fija router.ORDER.
RULES_BY_NAME: dict[str, tuple[re.Pattern[str], Handler]] = {}


def rule(name: str, pattern: str) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        if name in RULES_BY_NAME:
            raise ValueError(f"Regla repetida: {name}")
        RULES_BY_NAME[name] = (re.compile(pattern), fn)
        return fn

    return deco


def _call(rule_name: str, tool: str, **arguments: object) -> Route:
    return Route([ToolCall(tool, {k: v for k, v in arguments.items() if v is not None})], rule_name)


# --- atajos de teclado (send_hotkey) ---

# Se mira si la app ya tiene ventana: si no, abrirla ya deja una pestaña nueva.
_find_windows = windows.find_windows


# --- deshacer, cerrar y archivos (bloque 3b) ---

_NUMWORD = "|".join(sorted([*NUMBER_WORDS, *_TENS], key=len, reverse=True))
_N = rf"\d{{1,3}}|(?:{_NUMWORD})(?: y (?:{_NUMWORD}))?"


def _original(fragment: str) -> str:
    """El trozo tal como lo dijo el usuario (con tildes y mayúsculas): «mama» → «mamá»."""
    words = _RAW.get().split()
    want = fragment.split()
    clean = [_clean(w) for w in words]
    for i in range(len(words) - len(want) + 1):
        if clean[i : i + len(want)] == want:
            return " ".join(words[i : i + len(want)]).strip(".,;:!?¡¿")
    return fragment


# --- ventanas ---


_WIN_PREFIX = re.compile(
    r"^(?:(?:la\s+ventana|ventana)\s+(?:de(?:l)?\s+)?|"
    r"(?:el\s+programa|programa)\s+(?:de\s+)?|"
    r"(?:la\s+(?:aplicacion|app))\s+(?:de\s+)?|"
    r"(?:el|la|los|las)\s+)+"
)


def _window_name(raw: str | None) -> str | None:
    raw = (raw or "").strip()
    if raw in _THIS_WINDOW:
        return None
    cleaned = _WIN_PREFIX.sub("", raw).strip()
    return None if cleaned in _THIS_WINDOW else cleaned


_RAW_POLITE = re.compile(r"(?:,\s*|\s+)(?:por favor|porfa|gracias)$", re.I)


def _clean_dictated(raw: str) -> str:
    text = raw.strip()
    if (text.endswith(".") and not text.endswith("...")) or (
        text.endswith(("!", "?")) and "¡" not in text and "¿" not in text
    ):
        text = text[:-1].rstrip()
    return text.strip(" «»\"'")


TYPO_RATIO = 85


def _fix_typo(name: str | None, index: SystemIndex) -> str | None:
    """«crome» (Whisper) → «Google Chrome»: solo si se parece mucho a una sola app y no es ya
    uno de sus nombres; si no, el nombre tal cual (window_layout busca la ventana)."""
    if not name:
        return name
    best = index.confident(index.resolve(name, {Kind.APP, Kind.GAME}))
    # Solo parecido letra a letra («crome»/«chrome»), no por estar dentro de un nombre más
    # largo: «navegador» no es «Opera GX navegador» (window_layout busca el predeterminado).
    if best is None or best.alias == name or fuzz.ratio(name, best.alias) < TYPO_RATIO:
        return name
    return best.entry.name
