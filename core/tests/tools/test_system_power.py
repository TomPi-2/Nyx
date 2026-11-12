from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from nyx.executor import Confirmation, Executor, ToolCall
from nyx.safety.action_log import ActionLog
from nyx.tools.base import Category, GamePolicy, Risk, ToolContext
from nyx.tools.registry import ToolRegistry
from nyx.tools.system_power import PowerAction, SystemPower, run_power_action


def test_system_power_metadata() -> None:
    tool = SystemPower()
    assert tool.name == "system_power"
    assert tool.risk is Risk.GREEN
    assert tool.game_policy is GamePolicy.BLOCKED
    assert tool.category is Category.SYSTEM


async def test_lock_is_green_and_runs_without_confirmation(ctx: ToolContext) -> None:
    called: list[PowerAction] = []

    def runner(action: PowerAction) -> bool:
        called.append(action)
        return True

    tool = SystemPower(runner=runner)
    confirmations: list[Confirmation] = []

    async def confirm(c: Confirmation) -> bool:
        confirmations.append(c)
        return True

    ex = Executor(ToolRegistry([tool]), ctx, confirm=confirm)
    res = await ex.run(ToolCall("system_power", {"action": "lock"}))
    assert res.ok
    assert called == ["lock"]
    assert confirmations == []
    assert res.display == "Equipo bloqueado"


@pytest.mark.parametrize("action", ["sleep", "restart", "shutdown"])
async def test_sleep_restart_shutdown_are_red_and_require_confirmation(
    ctx: ToolContext, action: PowerAction
) -> None:
    called: list[PowerAction] = []

    def runner(a: PowerAction) -> bool:
        called.append(a)
        return True

    tool = SystemPower(runner=runner)
    confirmations: list[Confirmation] = []

    async def deny(c: Confirmation) -> bool:
        confirmations.append(c)
        return False

    ex_deny = Executor(ToolRegistry([tool]), ctx, confirm=deny)
    cancelled = await ex_deny.run(ToolCall("system_power", {"action": action}))
    assert not cancelled.ok
    assert cancelled.data.get("cancelled") is True
    assert called == []
    assert len(confirmations) == 1

    async def accept(c: Confirmation) -> bool:
        confirmations.append(c)
        return True

    ex_accept = Executor(ToolRegistry([tool]), ctx, confirm=accept)
    res = await ex_accept.run(ToolCall("system_power", {"action": action}))
    assert res.ok
    assert called == [action]


async def test_action_log_keeps_the_real_risk(ctx: ToolContext, tmp_path: Path) -> None:
    """Apagar queda como rojo en el registro, no como el verde de la herramienta."""

    async def accept(c: Confirmation) -> bool:
        return True

    action_log = ActionLog(tmp_path / "log")
    ex = Executor(
        ToolRegistry([SystemPower(runner=lambda a: True)]),
        ctx,
        confirm=accept,
        action_log=action_log,
    )
    await ex.run(ToolCall("system_power", {"action": "lock"}))
    await ex.run(ToolCall("system_power", {"action": "shutdown"}))
    assert [r["risk"] for r in action_log.read()] == ["green", "red"]


async def test_system_power_handles_runner_failure_and_exception(ctx: ToolContext) -> None:
    tool_false = SystemPower(runner=lambda _: False)
    ex_false = Executor(ToolRegistry([tool_false]), ctx)
    res_false = await ex_false.run(ToolCall("system_power", {"action": "lock"}))
    assert not res_false.ok
    assert "No he podido" in res_false.message

    def boom(_: PowerAction) -> bool:
        raise OSError("denegado")

    tool_err = SystemPower(runner=boom)
    ex_err = Executor(ToolRegistry([tool_err]), ctx)
    res_err = await ex_err.run(ToolCall("system_power", {"action": "lock"}))
    assert not res_err.ok


def test_run_power_action_never_uses_force_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[list[str]] = []

    def fake_run(cmd: list[str], **_: object) -> SimpleNamespace:
        commands.append(cmd)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert run_power_action("shutdown") is True
    assert run_power_action("restart") is True
    assert commands == [["shutdown", "/s", "/t", "0"], ["shutdown", "/r", "/t", "0"]]
    for cmd in commands:
        assert "/f" not in cmd
