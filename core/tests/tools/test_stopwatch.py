from __future__ import annotations

import pytest
from pydantic import ValidationError

from nyx.tools.base import Category, GamePolicy, Risk, ToolContext
from nyx.tools.stopwatch import Stopwatch, StopwatchParams


def test_metadata() -> None:
    tool = Stopwatch()
    assert tool.name == "stopwatch"
    assert tool.risk is Risk.GREEN
    assert tool.game_policy is GamePolicy.ALLOWED
    assert tool.category is Category.TIME
    assert tool.observe is True


async def test_stopwatch_lifecycle(ctx: ToolContext) -> None:
    now = 100.0
    tool = Stopwatch(clock=lambda: now)

    idle = await tool.run(StopwatchParams(action="status"), ctx)
    assert idle.ok and idle.data == {"running": False, "elapsed_s": 0}
    assert idle.display == "Sin iniciar"

    stop_idle = await tool.run(StopwatchParams(action="stop"), ctx)
    assert not stop_idle.ok

    start = await tool.run(StopwatchParams(action="start"), ctx)
    assert start.ok and start.data == {"running": True, "elapsed_s": 0}

    # Con 0 segundos no debe fallar el formato hablado.
    zero = await tool.run(StopwatchParams(action="status"), ctx)
    assert zero.ok and "0 segundos" in zero.message and zero.display == "0 s"

    now += 80.0
    running = await tool.run(StopwatchParams(action="status"), ctx)
    assert running.ok
    assert running.display == "1 min 20 s"
    assert "1 minuto y 20 segundos" in running.message
    assert running.data == {"running": True, "elapsed_s": 80}

    now += 45.0
    stopped = await tool.run(StopwatchParams(action="stop"), ctx)
    assert stopped.ok
    assert stopped.display == "2 min 5 s"
    assert "2 minutos y 5 segundos" in stopped.message
    assert stopped.data == {"running": False, "elapsed_s": 125}

    after = await tool.run(StopwatchParams(action="status"), ctx)
    assert after.ok and after.data == {"running": False, "elapsed_s": 125}
    assert "parado" in after.message


def test_invalid_action_rejected() -> None:
    with pytest.raises(ValidationError):
        StopwatchParams.model_validate({"action": "pause"})
