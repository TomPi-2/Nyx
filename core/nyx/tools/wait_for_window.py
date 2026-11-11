"""wait_for_window: espera a que aparezca una ventana (verde). La usa el ejecutor en los
planes de varios pasos: «abre el bloc de notas y…» (SPEC sección 6)."""

from __future__ import annotations

import asyncio
import time

from pydantic import Field

from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult
from nyx.tools.focus_window import process_for
from nyx.winapi import windows

POLL_S = 0.2


class WaitForWindowParams(Params):
    name: str = Field(min_length=1, max_length=100, description="App o título de la ventana")
    timeout_s: float = Field(default=10.0, ge=0.5, le=30.0)


class WaitForWindow(Tool[WaitForWindowParams]):
    name = "wait_for_window"
    description = "Espera a que se abra la ventana de una app antes del siguiente paso."
    risk = Risk.GREEN
    game_policy = GamePolicy.ALLOWED
    category = Category.WINDOWS
    params_model = WaitForWindowParams
    # Las esperas las pone el ejecutor solo (with_waits): el modelo no la necesita (6.18).
    llm_visible = False
    timeout_s = 31.0

    async def run(self, params: WaitForWindowParams, ctx: ToolContext) -> ToolResult:
        process = process_for(ctx, params.name)
        deadline = time.monotonic() + params.timeout_s
        while True:
            found = await asyncio.to_thread(windows.find_windows, params.name, process)
            if found:
                return ToolResult(ok=True, message=f"Ventana lista: {found[0].title}")
            if time.monotonic() >= deadline:
                return ToolResult.fail(f"{params.name} no ha abierto ninguna ventana")
            await asyncio.sleep(POLL_S)
