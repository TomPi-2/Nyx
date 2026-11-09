"""Voces disponibles. Predeterminada: «lola» (Pocket TTS), mujer.

Pruebas de escucha del 2026-11-09 (docs/benchmarks/tts-TomPi-20261109.jsonl): lola es la
voz femenina en español que mejor suena de las libres que funcionan en la CPU; davefx y
daniela (Piper) son las mejores alternativas. sharvard F (mujer, España) sonaba robótica.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Engine(StrEnum):
    POCKET = "pocket"
    PIPER = "piper"


@dataclass(frozen=True, slots=True)
class Voice:
    id: str
    label: str  # lo que verá el usuario en Ajustes
    engine: Engine
    # Pocket: nombre de la voz del catálogo de Kyutai. Piper: claves en nyx.models.MODELS.
    name: str = ""
    model: str = ""
    config: str = ""
    speaker: int | None = None


VOICES: dict[str, Voice] = {
    v.id: v
    for v in (
        Voice("lola", "Mujer · Lola", Engine.POCKET, name="lola"),
        Voice(
            "davefx",
            "Hombre · España",
            Engine.PIPER,
            model="voice-davefx",
            config="voice-davefx-config",
        ),
        Voice(
            "daniela",
            "Mujer · Argentina",
            Engine.PIPER,
            model="voice-daniela",
            config="voice-daniela-config",
        ),
    )
}
DEFAULT_VOICE = "lola"


def voice_for(voice_id: str) -> Voice:
    """La voz pedida, o la predeterminada si no existe (ajustes antiguos: «ef_dora»…)."""
    return VOICES.get(voice_id, VOICES[DEFAULT_VOICE])
