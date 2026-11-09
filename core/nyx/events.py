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
class BubbleAction:
    """Botón en pastilla de una burbuja (Confirmar, Cancelar, Deshacer)."""

    id: str
    label: str
    primary: bool = False


@dataclass(frozen=True, slots=True)
class BubbleShown:
    """Burbuja de respuesta: dato destacado grande + línea secundaria (+ botones)."""

    display: str
    secondary: str | None = None
    actions: tuple[BubbleAction, ...] = ()


@dataclass(frozen=True, slots=True)
class BubbleHidden:
    pass


# Interfaz → núcleo


@dataclass(frozen=True, slots=True)
class TextEntered:
    """El usuario ha escrito una petición en el campo de texto (atajo Win+Alt+N)."""

    text: str


@dataclass(frozen=True, slots=True)
class TalkKey:
    """Atajo de hablar pulsado o soltado."""

    pressed: bool


@dataclass(frozen=True, slots=True)
class ActionChosen:
    """El usuario ha pulsado un botón de la burbuja."""

    id: str
