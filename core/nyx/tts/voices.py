"""Voces disponibles (Piper). La predeterminada es de mujer con acento de España.

Elegidas en la prueba de escucha del 2026-11-09 (docs/benchmarks/tts-TomPi-20261109.jsonl):
suenan más naturales que Kokoro en español y tardan ~0,04 s por frase en la CPU.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Voice:
    id: str
    label: str  # lo que verá el usuario en Ajustes
    model: str  # clave del .onnx en nyx.models.MODELS
    config: str  # clave del .onnx.json
    speaker: int | None = None  # voces con varios hablantes


VOICES: dict[str, Voice] = {
    v.id: v
    for v in (
        Voice("sharvard_f", "Mujer · España", "voice-sharvard", "voice-sharvard-config", speaker=1),
        Voice("davefx", "Hombre · España", "voice-davefx", "voice-davefx-config"),
        Voice("daniela", "Mujer · Argentina", "voice-daniela", "voice-daniela-config"),
    )
}
DEFAULT_VOICE = "sharvard_f"


def voice_for(voice_id: str) -> Voice:
    """La voz pedida, o la predeterminada si no existe (ajustes antiguos: «ef_dora»…)."""
    return VOICES.get(voice_id, VOICES[DEFAULT_VOICE])
