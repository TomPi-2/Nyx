from __future__ import annotations

from nyx.executor import Executor, ToolCall
from nyx.tools.base import Category, GamePolicy, Risk, ToolContext
from nyx.tools.registry import ToolRegistry
from nyx.tools.toggle_wifi import ToggleWifi


def test_toggle_wifi_metadata() -> None:
    tool = ToggleWifi()
    assert tool.name == "toggle_wifi"
    assert tool.risk is Risk.YELLOW
    assert tool.game_policy is GamePolicy.DEFERRED
    assert tool.category is Category.SYSTEM


async def test_toggle_wifi_switches_and_undoes_to_previous_state(ctx: ToolContext) -> None:
    state = {"on": True}

    def switcher(enabled: bool | None) -> tuple[bool, bool]:
        was = state["on"]
        new = (not was) if enabled is None else enabled
        state["on"] = new
        return new, was

    ex = Executor(ToolRegistry([ToggleWifi(switcher=switcher)]), ctx)
    res = await ex.run(ToolCall("toggle_wifi", {"enabled": False}))
    assert res.ok
    assert state["on"] is False
    assert res.display == "Wi-Fi desactivado"
    assert res.data == {"enabled": False, "previous": True, "undo_id": res.data["undo_id"]}

    entry = ctx.undo.take()
    assert entry is not None
    undo_msg = await entry.action()
    assert state["on"] is True
    assert "activado" in undo_msg


async def test_toggle_wifi_handles_missing_adapter_and_permissions(ctx: ToolContext) -> None:
    def missing(_: bool | None) -> tuple[bool, bool]:
        raise LookupError("wifi")

    ex_missing = Executor(ToolRegistry([ToggleWifi(switcher=missing)]), ctx)
    res_missing = await ex_missing.run(ToolCall("toggle_wifi", {}))
    assert not res_missing.ok
    assert "adaptador Wi-Fi" in res_missing.message

    def denied(_: bool | None) -> tuple[bool, bool]:
        raise PermissionError("denied")

    ex_denied = Executor(ToolRegistry([ToggleWifi(switcher=denied)]), ctx)
    res_denied = await ex_denied.run(ToolCall("toggle_wifi", {"enabled": True}))
    assert not res_denied.ok
    assert "permite" in res_denied.message
