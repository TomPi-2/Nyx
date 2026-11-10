from pathlib import Path

import pytest

from nyx.events import TextEntered
from nyx.wake.activations import ERROR_STEP, MAX_OFFSET, ActivationLog, is_not_for_you
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
