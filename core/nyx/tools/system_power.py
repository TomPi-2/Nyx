"""system_power: bloquear (verde), suspender, reiniciar o apagar (rojas, bloqueadas en partida).

Apagar y reiniciar usan `shutdown /s /t 0` y `shutdown /r /t 0`, nunca `/f` (forzado), para que
Windows avise si quedan archivos sin guardar.
"""

from __future__ import annotations

import asyncio
import ctypes
import logging
import subprocess
from collections.abc import Callable
from typing import Literal

from pydantic import Field

from nyx.tools.base import (
    Category,
    GamePolicy,
    Params,
    Prepared,
    Risk,
    Tool,
    ToolContext,
    ToolResult,
)

log = logging.getLogger(__name__)

PowerAction = Literal["lock", "sleep", "restart", "shutdown"]

_SUMMARIES: dict[PowerAction, tuple[str, str]] = {
    "lock": ("Bloquear el equipo", ""),
    "sleep": ("Suspender el equipo", "Entrará en modo de suspensión"),
    "restart": ("Reiniciar el equipo", "Se cerrarán las aplicaciones abiertas"),
    "shutdown": ("Apagar el equipo", "Se cerrarán las aplicaciones abiertas"),
}

_MESSAGES: dict[PowerAction, str] = {
    "lock": "Equipo bloqueado",
    "sleep": "Suspendiendo el equipo",
    "restart": "Reiniciando el equipo",
    "shutdown": "Apagando el equipo",
}


def run_power_action(action: PowerAction) -> bool:
    """Ejecuta la acción de energía en Windows."""
    if action == "lock":
        return bool(ctypes.windll.user32.LockWorkStation())
    if action == "sleep":
        # bHibernate=0 (suspender), bForce=0 (sin forzar), bWakeupEventsDisabled=0
        return bool(ctypes.windll.powrprof.SetSuspendState(0, 0, 0))
    flag = "/r" if action == "restart" else "/s"
    res = subprocess.run(
        ["shutdown", flag, "/t", "0"],
        check=False,
        capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return res.returncode == 0


class SystemPowerParams(Params):
    action: PowerAction = Field(description="lock, sleep, restart o shutdown")


class SystemPower(Tool[SystemPowerParams]):
    name = "system_power"
    description = (
        "Bloquea, suspende, reinicia o apaga el PC. "
        "Ej.: «bloquea el PC» (action=lock), «apaga el ordenador» (action=shutdown)."
    )
    risk = Risk.GREEN
    game_policy = GamePolicy.BLOCKED
    category = Category.SYSTEM
    params_model = SystemPowerParams

    def __init__(self, runner: Callable[[PowerAction], bool] = run_power_action) -> None:
        self._runner = runner

    async def prepare(self, params: SystemPowerParams, ctx: ToolContext) -> Prepared:
        summary, detail = _SUMMARIES[params.action]
        risk = Risk.GREEN if params.action == "lock" else Risk.RED
        return Prepared(summary=summary, detail=detail, risk=risk)

    async def execute(
        self, params: SystemPowerParams, ctx: ToolContext, prepared: Prepared
    ) -> ToolResult:
        try:
            ok = await asyncio.to_thread(self._runner, params.action)
        except Exception:
            log.warning("No se pudo ejecutar system_power(%s)", params.action, exc_info=True)
            return ToolResult.fail("No he podido hacerlo")
        if not ok:
            return ToolResult.fail("No he podido hacerlo")
        msg = _MESSAGES[params.action]
        return ToolResult(ok=True, message=msg, display=msg, data={"action": params.action})
