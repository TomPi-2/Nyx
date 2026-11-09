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
from typing import Any

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
    # Fase 2: palabra para Vosk. En la fase 4 la sustituye el modelo propio de «Nyx».
    word: str = "nix"
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
    num_ctx: int = Field(default=8192, ge=1024, le=32768)
    timeout_s: float = Field(default=8.0, ge=2.0, le=60.0)


class TTSSettings(_Section):
    enabled: bool = True
    # lola (mujer; Pocket TTS, predeterminada), davefx (hombre, España), daniela (mujer,
    # Argentina). Ver nyx/tts/voices.py.
    voice: str = "lola"
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


class ResponseSettings(_Section):
    # Peticiones escritas (Win+Alt+N): False = solo burbuja; True = también en voz alta.
    speak_typed: bool = False


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    version: int = SCHEMA_VERSION
    audio: AudioSettings = Field(default_factory=AudioSettings)
    wake: WakeSettings = Field(default_factory=WakeSettings)
    listen: ListenSettings = Field(default_factory=ListenSettings)
    stt: STTSettings = Field(default_factory=STTSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    tts: TTSSettings = Field(default_factory=TTSSettings)
    responses: ResponseSettings = Field(default_factory=ResponseSettings)


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
