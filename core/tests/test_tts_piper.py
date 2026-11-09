import json
from pathlib import Path

import numpy as np
import pytest

from nyx.models import MODELS, sha256_of
from nyx.settings import load_settings
from nyx.tts.piper import PiperTTS
from nyx.tts.voices import DEFAULT_VOICE, VOICES, Engine, voice_for


def test_catalog_points_to_models() -> None:
    assert DEFAULT_VOICE == "lola"
    assert VOICES["lola"].engine is Engine.POCKET
    for voice in VOICES.values():
        if voice.engine is not Engine.PIPER:
            continue
        assert MODELS[voice.model].filename.endswith(".onnx")
        assert MODELS[voice.config].filename == MODELS[voice.model].filename + ".json"


def test_unknown_voice_falls_back_to_default() -> None:
    assert voice_for("ef_dora").id == DEFAULT_VOICE
    assert voice_for("daniela").id == "daniela"


def test_kokoro_settings_are_migrated(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"tts": {"voice": "ef_dora", "lang": "es"}}), encoding="utf-8")
    assert load_settings(path).tts.voice == "lola"
    path.write_text(json.dumps({"tts": {"voice": "sharvard_f"}}), encoding="utf-8")
    assert load_settings(path).tts.voice == "lola"


@pytest.mark.parametrize("voice_id", [v.id for v in VOICES.values() if v.engine is Engine.PIPER])
async def test_real_voice_if_downloaded(voice_id: str) -> None:
    voice = VOICES[voice_id]
    model, config = MODELS[voice.model], MODELS[voice.config]
    if not model.path().exists() or not config.path().exists():
        pytest.skip("voz no descargada")
    assert sha256_of(model.path()) == model.sha256
    tts = PiperTTS(model.path(), config.path(), speaker=voice.speaker)
    await tts.load()
    audio = await tts.synthesize("Hola, soy Nyx.")
    assert tts.sample_rate == 22_050
    assert audio.dtype == np.float32 and 0.5 < audio.size / tts.sample_rate < 3.0
    assert float(np.abs(audio).max()) > 0.05  # no es silencio
