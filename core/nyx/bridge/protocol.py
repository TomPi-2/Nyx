"""Mensajes JSON entre el núcleo y la interfaz.

El tipo TypeScript equivalente está en ui/src/lib/protocol.ts: si cambias algo aquí,
cambia también allí y sube PROTOCOL_VERSION.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from nyx.events import NyxState

PROTOCOL_VERSION = 20


class _Msg(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# Interfaz → núcleo


class Hello(_Msg):
    """Primer mensaje obligatorio: autentica la conexión con el token de la sesión."""

    type: Literal["hello"] = "hello"
    token: str = Field(max_length=256)
    protocol: int


class TextInput(_Msg):
    """Petición escrita en el campo de texto."""

    type: Literal["text"] = "text"
    text: str = Field(min_length=1, max_length=2000)


class TalkKeyMsg(_Msg):
    """Atajo de hablar (pulsar o mantener)."""

    type: Literal["talk"] = "talk"
    pressed: bool


class ActionMsg(_Msg):
    """Botón pulsado en una burbuja."""

    type: Literal["action"] = "action"
    id: str = Field(min_length=1, max_length=64)


class SettingsGetMsg(_Msg):
    """v8: Ajustes pide los ajustes actuales."""

    type: Literal["settings_get"] = "settings_get"


class SettingsSetMsg(_Msg):
    """v8: Ajustes cambia algo (cambio parcial: {"game": {"mode": "normal"}})."""

    type: Literal["settings_set"] = "settings_set"
    patch: dict[str, Any]


class ExtMsg(_Msg):
    """v18: Ajustes → Extensiones pide algo (7.11)."""

    type: Literal["ext"] = "ext"
    action: Literal["list", "inspect", "install", "accept", "enable", "disable", "uninstall"]
    id: str = Field(default="", max_length=100)
    path: str = Field(default="", max_length=1024)


class SetupMsg(_Msg):
    """v12: asistente y Ajustes → Cerebro, Caché, Ayuda y Privacidad (nyx/setup/service.py)."""

    type: Literal["setup"] = "setup"
    action: Literal[
        "status",
        "download",
        "scan",
        "forget_shortcut",
        "forget_all_shortcuts",  # v16
        "mic_test_start",
        "mic_test_stop",
        "clear_samples",
        "clear_activations",
        "install_everything",  # v13
        "start_everything",  # v13
    ]
    arg: str = Field(default="", max_length=500)


class SetupFlowMsg(_Msg):
    """v19: primer arranque guiado (9.10): lo que se toca en su panel."""

    type: Literal["setup_flow"] = "setup_flow"
    action: Literal[
        "start",
        "next",
        "back",
        "skip",
        "pick",
        "size",
        "size_live",
        "mic",
        "speaker",  # v20: por dónde suena Nyx
        "data",
        "done",
        "install_everything",
        "close",
    ]
    value: str | int | bool | None = None


ClientMessage = Annotated[
    Hello
    | TextInput
    | TalkKeyMsg
    | ActionMsg
    | SettingsGetMsg
    | SettingsSetMsg
    | SetupMsg
    | SetupFlowMsg
    | ExtMsg,
    Field(discriminator="type"),
]
client_adapter: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)


# Núcleo → interfaz


class GlassInfo(_Msg):
    """v7: ajustes del motor de cristal (Ajustes → Apariencia; SPEC sección 12)."""

    quality: Literal["auto", "alto", "medio", "bajo"] = "auto"
    motion: Literal["siempre", "interaccion", "quieto"] = "siempre"
    edge: int = Field(default=5, ge=0, le=10)  # amplitud del borde: 0–10 → 0–7 px
    show_in_captures: bool = False


class Welcome(_Msg):
    type: Literal["welcome"] = "welcome"
    version: str
    protocol: int = PROTOCOL_VERSION
    indicator_size: int = 100  # v6: lado de la forma de Nyx en px (Ajustes → Apariencia)
    glass: GlassInfo = Field(default_factory=GlassInfo)  # v7
    # v10: apariencia personalizable (SPEC sección 12); los colores, en ui/src/theme/palette.ts.
    font: str = "segoe"
    nyx_color: str = "blanco"
    panel_tint: str = "gris"
    # v12: si no se ha pasado aún por el asistente de primer arranque, la isla lo abre.
    onboarding_done: bool = True
    # v18: aviso de «Nyx listo» (Apariencia; tarea 9.03): onda, nyx (el cuadrado) o nada.
    ready_indicator: str = "onda"


class StateMsg(_Msg):
    type: Literal["state"] = "state"
    state: NyxState


class LevelMsg(_Msg):
    """Nivel de audio a ~30 Hz para animar el indicador."""

    type: Literal["level"] = "level"
    rms: float = Field(ge=0.0, le=1.0)


class ActionButton(_Msg):
    id: str
    label: str
    primary: bool = False


class LongSectionMsg(_Msg):
    """v17: una parte de una respuesta estructurada («Ingredientes», «Pasos»)."""

    title: str
    items: list[str]
    ordered: bool = False


class BubbleMsg(_Msg):
    type: Literal["bubble"] = "bubble"
    display: str
    secondary: str | None = None
    actions: list[ActionButton] = []
    alert: bool = False  # v4: alarmas y avisos (la interfaz lanza la notificación de Windows)
    # v7: qué panel la muestra y cuánto dura (cuenta atrás de confirmar y deshacer).
    kind: Literal["response", "confirm", "undo", "alert", "long"] = "response"
    expires_s: float | None = None
    # v17 (6.28): panel largo. El texto entero, las secciones (receta, pasos, lista) o, con
    # `reading`, nada aún: llega frase a frase con `reading` (ReadingMsg).
    text: str = ""
    sections: list[LongSectionMsg] = []
    reading: bool = False


class ReadingMsg(_Msg):
    """v17: panel largo, una frase que empieza a sonar; se escribe en `duration_s` (0: ya)."""

    type: Literal["reading"] = "reading"
    text: str
    duration_s: float = Field(ge=0.0)


class PanelNoteMsg(_Msg):
    """v17: aviso al pie del panel largo; con `undo_action`, botón Deshacer con ese id."""

    type: Literal["panel_note"] = "panel_note"
    text: str
    undo_action: str | None = None


class BubbleHideMsg(_Msg):
    type: Literal["bubble_hide"] = "bubble_hide"


class GameMsg(_Msg):
    """v5: partida en marcha y «Nyx en partida» (la interfaz no aparece sobre el juego)."""

    type: Literal["game"] = "game"
    active: bool
    mode: Literal["off", "voice", "normal"] = "voice"
    # v11: monitor del juego («\.DISPLAY1»); "" si no se sabe.
    monitor: str = ""


class ToolInfo(_Msg):
    """v8: herramienta para la lista de políticas en partida (Ajustes → Modo partida)."""

    name: str
    risk: Literal["green", "yellow", "red"]
    game_policy: Literal["allowed", "deferred", "blocked"]


class VoiceInfo(_Msg):
    """v10: voz para elegir en Ajustes → Voz."""

    id: str
    label: str


class SettingsMsg(_Msg):
    """v8: ajustes actuales; se manda a todas las ventanas cada vez que cambian."""

    type: Literal["settings"] = "settings"
    data: dict[str, Any]
    restart: list[str] = []  # lo cambiado que se aplica al reiniciar Nyx
    error: str | None = None  # cambio rechazado
    tools: list[ToolInfo] = []
    # v10: para Ajustes → Voz (solo al leerlos; vacío al cambiar algo).
    inputs: list[str] = []
    outputs: list[str] = []
    voices: list[VoiceInfo] = []


class OpenSettingsMsg(_Msg):
    """v9: abrir la ventana de Ajustes («abre tus ajustes»), en una sección o en la primera."""

    type: Literal["open_settings"] = "open_settings"
    section: (
        Literal[
            "general",
            "apariencia",
            "activacion",
            "voz",
            "respuestas",
            "partida",
            "cerebro",
            "cache",
            "privacidad",
            "ayuda",
        ]
        | None
    ) = None


class ExtensionsMsg(_Msg):
    """v18: Ajustes → Extensiones (7.11): las instaladas y lo que trae un paquete."""

    type: Literal["extensions"] = "extensions"
    items: list[dict[str, Any]]
    dev_mode: bool
    inspect: dict[str, Any] | None = None
    error: str | None = None


class SetupStatusMsg(_Msg):
    """v12: modelos, Ollama, whisper, caché, atajos aprendidos y grabaciones."""

    type: Literal["setup_status"] = "setup_status"
    status: dict[str, Any]


class SetupProgressMsg(_Msg):
    """v12: progreso de una descarga."""

    type: Literal["setup_progress"] = "setup_progress"
    key: str
    label: str
    done_mb: float
    total_mb: float
    finished: bool = False
    error: str | None = None


class MicLevelMsg(_Msg):
    """v12: nivel del micrófono durante la prueba (0–1)."""

    type: Literal["mic_level"] = "mic_level"
    rms: float = Field(ge=0.0, le=1.0)


class SetupResultMsg(_Msg):
    """v12: cómo ha ido una acción (descargar, olvidar un atajo, borrar…)."""

    type: Literal["setup_result"] = "setup_result"
    action: str
    ok: bool
    message: str | None = None


class SetupFlowStateMsg(_Msg):
    """v19: estado del primer arranque guiado (paso, lo elegido, lo que dice Nyx…)."""

    type: Literal["setup_flow_state"] = "setup_flow_state"
    state: dict[str, Any]


class NyxReadyMsg(_Msg):
    """v20: Nyx está lista; la interfaz enseña la onda (9.04) o lo elegido en Apariencia."""

    type: Literal["nyx_ready"] = "nyx_ready"


ServerMessage = Annotated[
    Welcome
    | StateMsg
    | LevelMsg
    | BubbleMsg
    | ReadingMsg
    | PanelNoteMsg
    | BubbleHideMsg
    | GameMsg
    | SettingsMsg
    | OpenSettingsMsg
    | SetupStatusMsg
    | ExtensionsMsg
    | SetupProgressMsg
    | MicLevelMsg
    | SetupResultMsg
    | SetupFlowStateMsg
    | NyxReadyMsg,
    Field(discriminator="type"),
]
server_adapter: TypeAdapter[ServerMessage] = TypeAdapter(ServerMessage)
