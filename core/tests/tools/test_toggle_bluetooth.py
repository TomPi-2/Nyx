from __future__ import annotations

from nyx.executor import Executor, ToolCall
from nyx.tools.base import Category, GamePolicy, Risk, ToolContext
from nyx.tools.registry import ToolRegistry
from nyx.tools.toggle_bluetooth import ToggleBluetooth


def test_toggle_bluetooth_metadata() -> None:
    tool = ToggleBluetooth()
    assert tool.name == "toggle_bluetooth"
    assert tool.risk is Risk.YELLOW
    assert tool.game_policy is GamePolicy.DEFERRED
    assert tool.category is Category.SYSTEM


async def test_toggle_bluetooth_switches_and_undoes_to_previous_state(ctx: ToolContext) -> None:
    state = {"on": False}

    def switcher(enabled: bool | None) -> tuple[bool, bool]:
        was = state["on"]
        new = (not was) if enabled is None else enabled
        state["on"] = new
        return new, was

    ex = Executor(ToolRegistry([ToggleBluetooth(switcher=switcher)]), ctx)
    res = await ex.run(ToolCall("toggle_bluetooth", {}))
    assert res.ok
    assert state["on"] is True
    assert res.display == "Bluetooth activado"

    entry = ctx.undo.take()
    assert entry is not None
    undo_msg = await entry.action()
    assert state["on"] is False
    assert "desactivado" in undo_msg


async def test_toggle_bluetooth_handles_missing_adapter(ctx: ToolContext) -> None:
    def missing(_: bool | None) -> tuple[bool, bool]:
        raise LookupError("bluetooth")

    ex = Executor(ToolRegistry([ToggleBluetooth(switcher=missing)]), ctx)
    res = await ex.run(ToolCall("toggle_bluetooth", {"enabled": False}))
    assert not res.ok
    assert "adaptador Bluetooth" in res.message
