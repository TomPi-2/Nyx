"""Eventos internos del núcleo que circulan por el bus."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal


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


#: Qué panel la muestra (SPEC sección 11): respuesta, confirmación, deshacer o aviso.
BubbleKind = Literal["response", "confirm", "undo", "alert"]


@dataclass(frozen=True, slots=True)
class BubbleShown:
    """Burbuja de respuesta: dato destacado grande + línea secundaria (+ botones)."""

    display: str
    secondary: str | None = None
    actions: tuple[BubbleAction, ...] = ()
    alert: bool = False  # alarmas y avisos: además, notificación de Windows
    kind: BubbleKind = "response"
    # Cuánto dura (confirmación que caduca, tiempo para deshacer): la interfaz lo enseña.
    expires_s: float | None = None


@dataclass(frozen=True, slots=True)
class BubbleHidden:
    pass


@dataclass(frozen=True, slots=True)
class OpenSettingsWindow:
    """Abrir la ventana de Ajustes de Nyx (herramienta open_nyx_settings)."""

    section: str | None = None


@dataclass(frozen=True, slots=True)
class SettingsChanged:
    """Ajustes actuales tras leerlos o cambiarlos desde Ajustes (SPEC sección 13)."""

    data: dict[str, Any]
    restart: tuple[str, ...] = ()  # lo cambiado que se aplica al reiniciar Nyx
    error: str | None = None  # cambio rechazado (no se ha aplicado nada)
    # Al leerlos: micrófonos y altavoces que hay ahora (Ajustes → Voz).
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()


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


@dataclass(frozen=True, slots=True)
class SettingsRequested:
    """Ajustes pide leerlos (`patch` None) o cambiarlos (cambio parcial)."""

    patch: dict[str, Any] | None = None


# Asistente de primer arranque y Ajustes → Cerebro, Caché, Ayuda y Privacidad (fase 5d‑2).

#: Lo que se le puede pedir a SetupService (nyx/setup/service.py).
SetupAction = Literal[
    "status",
    "download",
    "scan",
    "forget_shortcut",
    "mic_test_start",
    "mic_test_stop",
    "clear_samples",
    "clear_activations",
    "install_everything",
    "start_everything",
]


@dataclass(frozen=True, slots=True)
class SetupRequested:
    action: SetupAction
    arg: str = ""


@dataclass(frozen=True, slots=True)
class SetupStatusChanged:
    """Estado completo: modelos, Ollama, whisper, caché, atajos aprendidos y grabaciones."""

    status: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SetupProgress:
    """Progreso de una descarga (modelo del catálogo u Ollama)."""

    key: str
    label: str
    done_mb: float
    total_mb: float
    finished: bool = False
    error: str | None = None


@dataclass(frozen=True, slots=True)
class MicLevelChanged:
    """Nivel del micrófono durante la prueba del asistente (0–1)."""

    rms: float


@dataclass(frozen=True, slots=True)
class SetupResult:
    action: str
    ok: bool
    message: str | None = None
