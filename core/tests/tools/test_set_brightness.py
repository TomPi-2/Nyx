from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from nyx.executor import Executor, ToolCall
from nyx.tools.base import Category, GamePolicy, Risk, ToolContext
from nyx.tools.registry import ToolRegistry
from nyx.tools.set_brightness import SetBrightness, set_screen_brightness


def test_set_brightness_metadata() -> None:
    tool = SetBrightness()
    assert tool.name == "set_brightness"
    assert tool.risk is Risk.GREEN
    assert tool.game_policy is GamePolicy.ALLOWED
    assert tool.category is Category.SYSTEM


async def test_set_brightness_level_and_change(ctx: ToolContext) -> None:
    state = {"level": 50}

    def getter() -> int | None:
        return state["level"]

    def setter(val: int) -> int | None:
        state["level"] = val
        return val

    ex = Executor(ToolRegistry([SetBrightness(getter=getter, setter=setter)]), ctx)

    res_set = await ex.run(ToolCall("set_brightness", {"level": 80}))
    assert res_set.ok
    assert res_set.data["level"] == 80
    assert state["level"] == 80

    res_down = await ex.run(ToolCall("set_brightness", {"change": -30}))
    assert res_down.ok
    assert res_down.data["level"] == 50

    res_clamp = await ex.run(ToolCall("set_brightness", {"change": 90}))
    assert res_clamp.ok
    assert res_clamp.data["level"] == 100


async def test_set_brightness_validation(ctx: ToolContext) -> None:
    ex = Executor(ToolRegistry([SetBrightness(getter=lambda: 50, setter=lambda v: v)]), ctx)
    assert not (await ex.run(ToolCall("set_brightness", {}))).ok
    assert not (await ex.run(ToolCall("set_brightness", {"level": 50, "change": 10}))).ok
    assert not (await ex.run(ToolCall("set_brightness", {"level": 120}))).ok


async def test_set_brightness_external_monitor_without_ddc(ctx: ToolContext) -> None:
    ex_none = Executor(
        ToolRegistry([SetBrightness(getter=lambda: None, setter=lambda _: None)]), ctx
    )
    res_change = await ex_none.run(ToolCall("set_brightness", {"change": -20}))
    assert not res_change.ok
    assert "DDC/CI" in (res_change.secondary or "")

    def boom(_: int) -> int | None:
        raise RuntimeError("NoValidDisplayError")

    ex_err = Executor(ToolRegistry([SetBrightness(getter=lambda: 50, setter=boom)]), ctx)
    res_set = await ex_err.run(ToolCall("set_brightness", {"level": 40}))
    assert not res_set.ok
    assert "DDC/CI" in (res_set.secondary or "")


def test_no_monitor_answering_is_not_a_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Si ningún monitor contesta, no se da el brillo por cambiado."""
    fake = SimpleNamespace(
        get_brightness=lambda: [None], set_brightness=lambda level, no_return=False: [None]
    )
    monkeypatch.setitem(sys.modules, "screen_brightness_control", fake)
    assert set_screen_brightness(40) is None
    fake.set_brightness = lambda level, no_return=False: [None, 40]
    assert set_screen_brightness(40) == 40
