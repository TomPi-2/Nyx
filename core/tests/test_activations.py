from pathlib import Path

import pytest

from nyx.events import TextEntered
from nyx.wake.activations import (
    AUTO_COUNT,
    AUTO_DECAY_S,
    AUTO_MAX,
    AUTO_STEP,
    AUTO_WINDOW_S,
    ERROR_STEP,
    MAX_OFFSET,
    ActivationLog,
    is_not_for_you,
)
from tests.test_pipeline import Harness


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("Eso no era para ti.", True),
        ("no te he llamado", True),
        ("Falsa alarma", True),
        ("no hablaba contigo", True),
        ("¿qué hora es?", False),
        ("no era para ti la carta, era para Pablo", False),
    ],
)
def test_not_for_you(text: str, match: bool) -> None:
    assert is_not_for_you(text) is match


def test_error_raises_threshold_and_persists(tmp_path: Path) -> None:
    log = ActivationLog(tmp_path / "act", tmp_path / "state.json")
    log.record("OwnWakeWord", 0.61, True, "Nyx.")  # la que fue un error
    log.record("OwnWakeWord", 0.9, True, "Nyx, eso no era para ti.")  # la de ahora
    assert log.mark_previous_error() == pytest.approx(ERROR_STEP)
    assert ActivationLog(tmp_path / "act", tmp_path / "state.json").offset == pytest.approx(
        ERROR_STEP
    )
    assert log.mark_previous_error() is None  # ya no queda ninguna anterior
    files = list((tmp_path / "act").glob("*.jsonl"))
    assert files and '"error": true' in files[0].read_text(encoding="utf-8")


def test_offset_is_capped(tmp_path: Path) -> None:
    log = ActivationLog(tmp_path / "act", tmp_path / "state.json")
    for _ in range(20):
        log.record("x", 0.6, True)
        log.record("x", 0.9, True)
        log.mark_previous_error()
    assert log.offset == pytest.approx(MAX_OFFSET)


def test_rejected_activations_do_not_count_as_previous(tmp_path: Path) -> None:
    log = ActivationLog(tmp_path / "act", tmp_path / "state.json")
    log.record("x", 0.7, False, "Fakes.")  # whisper la descartó: nadie la vio
    log.record("x", 0.9, True)
    assert log.mark_previous_error() is None


async def test_pipeline_not_for_you_raises_engine_threshold(tmp_path: Path) -> None:
    h = Harness()

    class Engine:
        threshold = 0.5
        last_score = 0.6

        def process(self, frame: object) -> bool:
            return False

        def reset(self) -> None:
            pass

    engine = Engine()
    log = ActivationLog(tmp_path / "act", tmp_path / "state.json")
    h.p.wake = engine  # type: ignore[assignment]
    h.p.activations = log
    h.p._wake_threshold0 = 0.5
    log.record("Engine", 0.6, True)
    log.record("Engine", 0.9, True)
    await h.bus.publish(TextEntered("eso no era para ti"))
    await h.p.wait_idle()
    assert engine.threshold == pytest.approx(0.5 + ERROR_STEP)
    assert h.llm.requests == []
    assert h.bubbles[-1][0] == "Vale, lo apunto"
    await h.p.close()


# --- subida automática del umbral (6.22) ---


def test_three_discards_in_ten_minutes_raise_the_threshold(tmp_path: Path) -> None:
    log = ActivationLog(tmp_path / "act", tmp_path / "state.json")
    t = 1_000_000.0
    log.record("x", 0.6, False, "Gracias.", now=t)
    log.record("x", 0.6, False, "Gracias.", now=t + 60)
    assert log.auto_offset(t + 60) == 0.0
    log.record("x", 0.6, False, "Gracias.", now=t + 120)
    assert log.auto_offset(t + 120) == pytest.approx(AUTO_STEP)
    # Las confirmadas no cuentan, ni los descartes ya fuera de la ventana de 10 min.
    log.record("x", 0.9, True, "Nyx.", now=t + 130)
    log.record("x", 0.6, False, now=t + 200)
    log.record("x", 0.6, False, now=t + 200 + AUTO_WINDOW_S + 1)
    assert log.auto_offset(t + 900) == pytest.approx(AUTO_STEP)


def test_automatic_rise_is_capped_and_goes_down_when_quiet(tmp_path: Path) -> None:
    log = ActivationLog(tmp_path / "act", tmp_path / "state.json")
    t = 1_000_000.0
    for i in range(60):
        log.record("x", 0.6, False, now=t + i)
    assert log.auto_offset(t + 60) == pytest.approx(AUTO_MAX)
    last = t + 59
    assert log.auto_offset(last + AUTO_DECAY_S - 1) == pytest.approx(AUTO_MAX)
    assert log.auto_offset(last + AUTO_DECAY_S) == pytest.approx(AUTO_MAX - AUTO_STEP)
    assert log.auto_offset(last + 100 * AUTO_DECAY_S) == 0.0
    # No se guarda: al reiniciar, vuelve a empezar desde cero.
    assert ActivationLog(tmp_path / "act", tmp_path / "state.json").auto_offset() == 0.0


def test_false_activation_audio_only_when_allowed_and_capped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import numpy as np

    import nyx.wake.activations as activations

    clip = np.zeros(32_000, dtype=np.int16)
    log = ActivationLog(tmp_path / "act", tmp_path / "state.json")
    log.record("x", 0.6, False, "Gracias.", clip)
    assert not log.clips.exists()  # apagado por defecto
    monkeypatch.setattr(activations, "MAX_CLIPS", 3)
    log.save_clips = True
    log.record("x", 0.9, True, "Nyx.", clip)  # las buenas no se guardan
    assert not log.clips.exists()
    ids = [log.record("x", 0.6, False, "Gracias.", clip).id for _ in range(5)]
    saved = {p.stem for p in log.clips.glob("*.wav")}
    assert len(saved) == 3 and saved <= set(ids)


async def test_pipeline_discards_raise_and_lower_the_engine_threshold(tmp_path: Path) -> None:
    h = Harness()

    class Engine:
        threshold = 0.5
        last_score = 0.6

        def process(self, frame: object) -> bool:
            return False

        def reset(self) -> None:
            pass

    engine = Engine()
    log = ActivationLog(tmp_path / "act", tmp_path / "state.json")
    h.p.wake = engine  # type: ignore[assignment]
    h.p.activations = log
    h.p._wake_threshold0 = 0.5
    for _ in range(AUTO_COUNT):
        h.p._record_activation(False, "Gracias.")
    assert engine.threshold == pytest.approx(0.5 + AUTO_STEP)
    log._auto_since -= AUTO_DECAY_S  # pasa una hora sin descartes
    h.p._apply_threshold()
    assert engine.threshold == pytest.approx(0.5)
    await h.p.close()
