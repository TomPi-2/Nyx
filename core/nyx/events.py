"""Eventos internos del núcleo que circulan por el bus."""

from __future__ import annotations

from dataclasses import dataclass, field
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


#: Qué panel la muestra (SPEC sección 11): respuesta, confirmación, deshacer, aviso o la
#: respuesta larga (6.28: explicación, receta, pasos o lista).
BubbleKind = Literal["response", "confirm", "undo", "alert", "long"]


@dataclass(frozen=True, slots=True)
class LongSection:
    """Una parte de una respuesta estructurada («Ingredientes», «Pasos»)."""

    title: str
    items: tuple[str, ...]
    ordered: bool = False


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
    # Panel largo (6.28): el texto entero (petición escrita), las secciones (receta, pasos o
    # lista) o, con `reading`, nada aún: el texto llega frase a frase (`ReadingAppended`).
    text: str = ""
    sections: tuple[LongSection, ...] = ()
    reading: bool = False


@dataclass(frozen=True, slots=True)
class ReadingAppended:
    """Panel largo: una frase que empieza a sonar y lo que dura (se escribe a ese ritmo).
    `duration_s` 0: lo ya dicho antes de pasar al panel largo, de golpe."""

    text: str
    duration_s: float


@dataclass(frozen=True, slots=True)
class PanelNote:
    """Aviso al pie del panel largo («Copiado», «Nota guardada…»). Con `undo_action`, el
    botón Deshacer manda ese id; sin él, vuelven los botones de siempre."""

    text: str
    undo_action: str | None = None


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
class Announce:
    """Algo que Nyx dice por su cuenta si está libre (lo hecho al terminar una partida)."""

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
    "forget_all_shortcuts",
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


ExtAction = Literal[
    "list", "inspect", "install", "accept", "enable", "disable", "uninstall", "setting"
]


@dataclass(frozen=True, slots=True)
class ExtRequested:
    """Ajustes → Extensiones pide algo (0.7, tarea 7.11)."""

    action: ExtAction
    ext_id: str = ""
    path: str = ""  # el .nyxext elegido (inspect, install)
    key: str = ""  # setting: qué ajuste de la extensión (7.14)
    value: str = ""  # setting: su valor (vacío: quitarlo)


@dataclass(frozen=True, slots=True)
class ExtStatusChanged:
    """Las extensiones instaladas, el modo desarrollador y, si se pidió, lo que trae un
    paquete antes de instalarlo (`inspect`)."""

    items: list[dict[str, Any]]
    dev_mode: bool
    inspect: dict[str, Any] | None = None
    error: str | None = None
    #: Las de Tepnyx que vienen con Nyx y aún no tienes (o tienes más viejas; 7.14).
    official: list[dict[str, Any]] = field(default_factory=list)


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
class SetupFlowRequested:
    """Primer arranque guiado (9.10): lo que se toca en su panel («next», «pick»…)."""

    action: str
    value: str | int | bool | None = None


@dataclass(frozen=True, slots=True)
class SetupFlowChanged:
    """Primer arranque guiado: su estado entero, para el panel (setup/flow.py)."""

    state: dict[str, Any]


@dataclass(frozen=True, slots=True)
class UpdateOffered:
    """La app (Velopack) ha descargado una versión nueva y está lista para aplicarla (9.06)."""

    version: str


@dataclass(frozen=True, slots=True)
class UpdateApply:
    """El núcleo ha decidido aplicarla ya: la app para el núcleo y cambia de versión."""

    version: str


@dataclass(frozen=True, slots=True)
class NyxReady:
    """Nyx está lista (al arrancar, o al acabar el primer arranque y las descargas): la
    interfaz lo enseña según «Al estar lista» (onda, Nyx aparece y desaparece, o nada)."""


@dataclass(frozen=True, slots=True)
class SetupResult:
    action: str
    ok: bool
    message: str | None = None
