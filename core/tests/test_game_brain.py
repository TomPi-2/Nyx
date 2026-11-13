import pytest

from nyx.events import BubbleShown, TextEntered
from nyx.game.brain import GameBrain
from nyx.game.policy import GameGate
from nyx.settings.model import GameSettings


def make(brain: str) -> tuple[GameBrain, GameGate, list[str]]:
    gate = GameGate(GameSettings(brain=brain))  # type: ignore[arg-type]
    gate.active = True
    events: list[str] = []

    class LLM:
        async def unload(self) -> None:
            events.append("unload")

    async def warmup() -> None:
        events.append("warmup")

    return GameBrain(gate, LLM(), warmup), gate, events


async def test_the_brain_stays_by_default() -> None:
    # Un solo modelo (el 7B) y se queda en la gráfica: nada que cambiar al entrar o salir.
    brain, gate, events = make("auto")
    await brain.start()
    await brain.stop()
    assert events == [] and not gate.brain_off


async def test_only_orders_unloads_and_comes_back() -> None:
    brain, gate, events = make("off")
    await brain.start()
    assert gate.brain_off and events == ["unload"]
    await brain.stop()
    assert not gate.brain_off and events == ["unload", "warmup"]


async def test_questions_wait_when_there_is_no_brain() -> None:
    from tests.test_pipeline import Harness

    h = Harness(speak_typed=True)
    gate = GameGate(GameSettings())
    gate.active, gate.brain_off = True, True
    h.p.game = gate
    shown: list[BubbleShown] = []

    async def keep(e: BubbleShown) -> None:
        shown.append(e)

    h.bus.subscribe(BubbleShown, keep)
    await h.bus.publish(TextEntered("¿Qué es un agujero negro?"))
    await h.p.wait_idle()
    assert h.llm.requests == []  # ni se le pregunta
    assert shown[-1].display == "En partida no puedo pensarlo."
    assert h.tts.said[-1] == "En partida no puedo pensarlo. Pregúntamelo al terminar."
    await h.p.close()


@pytest.mark.parametrize("value", ["auto", "off"])
def test_setting_values(value: str) -> None:
    assert GameSettings(brain=value).brain == value  # type: ignore[arg-type]


def test_retired_14b_moves_to_the_7b() -> None:
    from nyx.settings.model import migrate

    data = migrate({"version": 1, "llm": {"model": "qwen2.5:14b"}})
    assert data["llm"]["model"] == "qwen2.5:7b"
    other = migrate({"version": 1, "llm": {"model": "llama3.1:8b"}})
    assert other["llm"]["model"] == "llama3.1:8b"  # solo se retira el 14B
