r"""Esquema de los ajustes y lectura/escritura de %APPDATA%\Nyx\settings.json (SPEC sección 13).

El archivo lleva un número de versión; `migrate` lo actualiza al cargar. Las claves que no
existen en el esquema se ignoran y las que faltan toman su valor por defecto, así que un
archivo antiguo o editado a mano nunca impide arrancar.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from nyx.paths import models_dir, roaming_dir

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1


class _Section(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=True)


class AudioSettings(_Section):
    # Nombre (o parte) del dispositivo; None = el predeterminado de Windows.
    input_device: str | None = None
    output_device: str | None = None


class WakeSettings(_Section):
    enabled: bool = True
    # Fase 4: modelo propio de «Nyx» (por defecto) o Vosk con gramática (alternativa).
    engine: Literal["propio", "vosk"] = "propio"
    # 1 = solo salta si está muy seguro … 10 = salta con poco (whisper verifica después).
    sensitivity: int = Field(default=6, ge=1, le=10)
    # Palabra para Vosk.
    word: str = "nix"
    # Palabra personalizada (p. ej. «oye lumen»): si hay, se usa Vosk con ella en vez de «Nyx».
    custom_word: str = ""
    # Audio anterior a la detección que se incluye en la frase («Nyx abre…» de una tirada).
    prebuffer_s: float = Field(default=1.5, ge=0.0, le=2.0)


class ListenSettings(_Section):
    silence_ms: int = Field(default=700, ge=200, le=3000)
    max_s: float = Field(default=15.0, ge=2.0, le=60.0)
    # Tras la palabra de activación, tiempo máximo para empezar a hablar.
    start_timeout_s: float = Field(default=4.0, ge=1.0, le=15.0)
    # Ventana de seguimiento: seguir hablando sin repetir «Nyx» (0 = desactivada).
    followup_s: float = Field(default=5.0, ge=0.0, le=30.0)


class STTSettings(_Section):
    # whisper-server.exe compilado con Vulkan (docs/benchmarks/README.md).
    server: Path | None = None
    model: Path = Field(default_factory=lambda: models_dir() / "ggml-large-v3-turbo-q5_0.bin")
    # Parte del nombre de la GPU; None = la primera tarjeta dedicada.
    gpu: str | None = None
    language: str = "es"


class LLMSettings(_Section):
    host: str = "http://127.0.0.1:11434"
    model: str = "qwen2.5:7b"
    # -1 = siempre cargado mientras Nyx esté abierto (SPEC sección 6); se libera al salir.
    keep_alive: int | str = -1
    # 12.288 desde la 6.18: el prefijo (sistema + herramientas) ya ocupaba 5.467 de 8.192.
    num_ctx: int = Field(default=12288, ge=1024, le=32768)
    timeout_s: float = Field(default=8.0, ge=2.0, le=60.0)


class TTSSettings(_Section):
    enabled: bool = True
    # lola (mujer; Pocket TTS, predeterminada), davefx (hombre, España), daniela (mujer,
    # Argentina). Ver nyx/tts/voices.py.
    voice: str = "lola"
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


ResponseTone = Literal["cercano", "neutro", "divertido"]


class ResponseSettings(_Section):
    # Peticiones escritas (Win+Alt+N): False = solo burbuja; True = también en voz alta.
    speak_typed: bool = False
    # Personalidad al responder (6.15): cambia un párrafo del prompt de sistema al arrancar.
    tone: ResponseTone = "cercano"


class GlassSettings(_Section):
    """Motor de cristal de los paneles (SPEC sección 12, «Motor de cristal»)."""

    # auto: el motor baja solo (batería, ahorro de energía…); un nivel concreto se respeta,
    # salvo en partida, donde siempre se pasa a «bajo».
    quality: Literal["auto", "alto", "medio", "bajo"] = "auto"
    motion: Literal["siempre", "interaccion", "quieto"] = "siempre"
    # Amplitud del borde líquido: barra de 0 a 10 que va de 0 a 7 px (5 = 3,5 px).
    edge: int = Field(default=5, ge=0, le=10)
    # Los paneles que capturan la pantalla no salen en capturas ni directos; con esto
    # activado usan el nivel «bajo» y salen.
    show_in_captures: bool = False


#: Opciones fijas de Apariencia (SPEC sección 12, «Apariencia personalizable»). Los colores de
#: cada una están en ui/src/theme/palette.ts.
Font = Literal["segoe", "manrope", "nunito"]
NyxColor = Literal[
    "blanco", "perla", "arena", "melocoton", "coral", "rojo", "rosa", "fucsia", "lavanda",
    "violeta", "azul_cielo", "azul", "turquesa", "menta", "verde", "lima", "amarillo",
    "ambar", "grafito",
]  # fmt: skip
PanelTint = Literal[
    "gris", "grafito", "azul_noche", "oceano", "bosque", "salvia", "ciruela", "vino", "rosa",
    "arena", "cobre", "lavanda",
]  # fmt: skip


class MonitorSettings(_Section):
    """En qué monitor aparece Nyx (SPEC sección 11, «Elección del monitor»)."""

    follow: Literal["cursor", "fixed"] = "cursor"
    # Nombre del dispositivo («\.DISPLAY2»); None o desconectado = el principal.
    fixed: str | None = Field(default=None, max_length=64)
    # Al cambiar de monitor estando visible: se encoge y aparece en el nuevo.
    transition: bool = True


class AppearanceSettings(_Section):
    """Apariencia (SPEC secciones 12 y 13)."""

    indicator_size: int = Field(default=100, ge=44, le=260)  # lado de la forma de Nyx (px)
    glass: GlassSettings = Field(default_factory=GlassSettings)
    font: Font = "segoe"
    nyx_color: NyxColor = "blanco"
    panel_tint: PanelTint = "gris"
    monitor: MonitorSettings = Field(default_factory=MonitorSettings)


class GameSettings(_Section):
    """Modo partida (SPEC sección 9)."""

    # off: Nyx no escucha en partida (salvo el atajo) · voice: voz sin interfaz en el monitor
    # del juego (recomendado) · normal: indicadores mínimos.
    mode: Literal["off", "voice", "normal"] = "voice"
    always: list[str] = Field(default_factory=list)  # ejecutables a tratar como juego
    never: list[str] = Field(default_factory=list)  # ejecutables que nunca son juego
    # Mover herramientas entre columnas: {"open_app": "allowed" | "deferred" | "blocked"}.
    policies: dict[str, Literal["allowed", "deferred", "blocked"]] = Field(default_factory=dict)
    low_priority: bool = True  # Nyx con prioridad baja mientras se juega
    unload_llm_after_min: int = Field(default=0, ge=0, le=240)  # 0 = no descargarlo
    # Cerebro en partida: auto = se queda en la gráfica (el 7B cuesta un 3,4 % de FPS);
    # off = «solo órdenes»: el modelo sale de la memoria mientras se juega (game/brain.py).
    brain: Literal["auto", "off"] = "auto"
    # En «solo voz» con varios monitores, si Nyx tuviera que salir en el del juego, sale en
    # este; None = automático (el principal, o el primero sin el juego).
    alt_monitor: str | None = Field(default=None, max_length=64)


class GeneralSettings(_Section):
    """Ajustes generales (SPEC sección 13): ciudad para el tiempo."""

    city: str = Field(default="", max_length=100)


class OnboardingSettings(_Section):
    """Asistente de primer arranque (SPEC sección 13)."""

    done: bool = False


class PrivacySettings(_Section):
    """Privacidad (SPEC sección 8). Desactivado por defecto: solo con permiso explícito."""

    usage_data: bool = False


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    version: int = SCHEMA_VERSION
    general: GeneralSettings = Field(default_factory=GeneralSettings)
    audio: AudioSettings = Field(default_factory=AudioSettings)
    wake: WakeSettings = Field(default_factory=WakeSettings)
    listen: ListenSettings = Field(default_factory=ListenSettings)
    stt: STTSettings = Field(default_factory=STTSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    tts: TTSSettings = Field(default_factory=TTSSettings)
    responses: ResponseSettings = Field(default_factory=ResponseSettings)
    game: GameSettings = Field(default_factory=GameSettings)
    appearance: AppearanceSettings = Field(default_factory=AppearanceSettings)
    onboarding: OnboardingSettings = Field(default_factory=OnboardingSettings)
    privacy: PrivacySettings = Field(default_factory=PrivacySettings)


def settings_path() -> Path:
    return roaming_dir() / "settings.json"


def migrate(data: dict[str, Any]) -> dict[str, Any]:
    """Actualiza un archivo de una versión anterior. Hoy solo existe la versión 1."""
    version = data.get("version", SCHEMA_VERSION)
    tts = data.get("tts")
    if isinstance(tts, dict) and (
        str(tts.get("voice", "")).startswith(("ef_", "em_")) or tts.get("voice") == "sharvard_f"
    ):
        tts["voice"] = "lola"  # voces retiradas (Kokoro; sharvard F) → la predeterminada
        tts.pop("lang", None)
    llm = data.get("llm")
    if isinstance(llm, dict) and llm.get("num_ctx") == 8192:
        llm["num_ctx"] = 12288  # tarea 6.18: con 8.192 no caben las herramientas de la 0.6
    if isinstance(llm, dict) and llm.get("model") == "qwen2.5:14b":
        # Decisión 2026-11-11: un solo modelo en la primera versión (el 14B era 8 veces más
        # lento sin acertar más, no cabe en 8 GB y junto a un juego da tirones).
        llm["model"] = "qwen2.5:7b"
    if not isinstance(version, int) or version > SCHEMA_VERSION:
        log.warning("Ajustes de una versión desconocida (%r): se leen tal cual", version)
    data["version"] = SCHEMA_VERSION
    return data


def load_settings(path: Path | None = None) -> Settings:
    """Lee los ajustes. Si el archivo no existe lo crea con los valores por defecto.

    Si está dañado, usa los valores por defecto sin sobrescribirlo, para no perder lo que
    el usuario tuviera.
    """
    path = path or settings_path()
    if not path.exists():
        settings = Settings()
        try:
            save_settings(settings, path)
        except OSError:
            log.warning("No se pudo crear %s", path, exc_info=True)
        return settings
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("el archivo no contiene un objeto JSON")
        return Settings.model_validate(migrate(data))
    except (OSError, ValueError, ValidationError):
        log.warning("Ajustes no válidos en %s: uso los valores por defecto", path, exc_info=True)
        return Settings()


def save_settings(settings: Settings, path: Path | None = None) -> None:
    """Escritura atómica: primero a un temporal y luego se sustituye."""
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, path)
