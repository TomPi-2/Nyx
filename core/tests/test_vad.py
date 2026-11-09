import math

import numpy as np
import pytest

from nyx.audio.capture import FRAME_S, FRAME_SAMPLES, rms_level
from nyx.audio.vad import Endpointer, EndReason, SileroVAD
from nyx.models import MODELS


def run(ep: Endpointer, probs: list[float]) -> tuple[EndReason | None, int]:
    for i, p in enumerate(probs):
        if (reason := ep.push(p)) is not None:
            return reason, i
    return None, len(probs)


def frames(seconds: float) -> int:
    return math.ceil(seconds / FRAME_S)


def test_ends_after_700ms_of_silence() -> None:
    ep = Endpointer(silence_ms=700)
    reason, i = run(ep, [0.9] * frames(1.0) + [0.05] * frames(2.0))
    assert reason is EndReason.SILENCE
    assert i == frames(1.0) + frames(0.7) - 1


def test_short_pauses_do_not_cut() -> None:
    probs = ([0.9] * frames(0.5) + [0.1] * frames(0.4)) * 4 + [0.9] * 5
    assert run(Endpointer(silence_ms=700), probs)[0] is None


def test_hysteresis_middle_values_count_as_speech() -> None:
    probs = [0.9] * 5 + [0.4] * frames(2.0)  # entre 0,35 y 0,5: sigue hablando
    assert run(Endpointer(silence_ms=700), probs)[0] is None


def test_no_speech_timeout() -> None:
    reason, i = run(Endpointer(start_timeout_s=1.0), [0.1] * frames(3.0))
    assert reason is EndReason.NO_SPEECH
    assert i == frames(1.0) - 1


def test_max_length() -> None:
    reason, _ = run(Endpointer(max_s=2.0), [0.9] * frames(5.0))
    assert reason is EndReason.MAX_LENGTH


def test_rms_level_range() -> None:
    assert rms_level(np.zeros(FRAME_SAMPLES, dtype=np.int16)) == 0.0
    loud = (np.sin(np.arange(FRAME_SAMPLES) / 5) * 20000).astype(np.int16)
    assert 0.9 < rms_level(loud) <= 1.0


@pytest.mark.skipif(not MODELS["vad"].path().exists(), reason="modelo Silero no descargado")
def test_silero_on_silence_and_tone() -> None:
    vad = SileroVAD(MODELS["vad"].path())
    silence = np.zeros(FRAME_SAMPLES, dtype=np.int16)
    assert max(vad(silence) for _ in range(10)) < 0.2
    vad.reset()
    with pytest.raises(ValueError):
        vad(np.zeros(100, dtype=np.int16))


def test_require_quiet_ignores_ongoing_speech() -> None:
    # Ya estaba hablando cuando se abrió la ventana: no cuenta aunque siga hablando.
    ep = Endpointer(start_timeout_s=2.0, require_quiet_s=0.3)
    reason, _ = run(ep, [0.9] * frames(3.0))
    assert reason is EndReason.NO_SPEECH and not ep.speech_started


def test_require_quiet_accepts_speech_after_silence() -> None:
    ep = Endpointer(start_timeout_s=3.0, require_quiet_s=0.3)
    run(ep, [0.9] * frames(0.5) + [0.1] * frames(0.4) + [0.9] * 3)
    assert ep.speech_started


def test_pause_s() -> None:
    ep = Endpointer()
    assert ep.pause_s == 0.0
    run(ep, [0.9] * 5 + [0.1] * frames(0.4))
    assert ep.pause_s >= 0.4
    ep.push(0.9)
    assert ep.pause_s == 0.0
