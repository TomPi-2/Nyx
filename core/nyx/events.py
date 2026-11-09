"""Eventos internos del núcleo que circulan por el bus."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class NyxState(StrEnum):
    """Estado visible de Nyx (SPEC sección 12, tabla de estados)."""

    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    CONFIRM = "confirm"
    ERROR = "error"
    MUTED = "muted"


@dataclass(frozen=True, slots=True)
class StateChanged:
    state: NyxState


@dataclass(frozen=True, slots=True)
class AudioLevel:
    """Nivel RMS normalizado (0–1) del micrófono o de la voz de Nyx."""

    rms: float


@dataclass(frozen=True, slots=True)
class BubbleShown:
    """Burbuja de respuesta: dato destacado grande + línea secundaria."""

    display: str
    secondary: str | None = None


@dataclass(frozen=True, slots=True)
class BubbleHidden:
    pass
