"""focus_window: trae al frente la ventana de una app abierta (verde)."""

from __future__ import annotations

import asyncio

from pydantic import Field

from nyx.index.model import Kind
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
from nyx.winapi import windows


class FocusWindowParams(Params):
    name: str = Field(min_length=1, max_length=100, description="App o título")


def process_for(ctx: ToolContext, name: str) -> str | None:
    """Ejecutable de la app con ese nombre, si la caché lo sabe (más fiable que el título)."""
    best = ctx.index.confident(ctx.index.resolve(name, {Kind.APP, Kind.GAME}))
    return best.entry.process if best else None


class FocusWindow(Tool[FocusWindowParams]):
    name = "focus_window"
    description = "Trae al frente una ventana abierta. Ej.: «cambia a Chrome» (name=Chrome)."
    risk = Risk.GREEN
    game_policy = GamePolicy.DEFERRED
    category = Category.WINDOWS
    params_model = FocusWindowParams

    async def prepare(self, params: FocusWindowParams, ctx: ToolContext) -> Prepared:
        """Si no hay ninguna ventana así, se dice ya (también en partida, antes de diferirlo)."""
        found = await asyncio.to_thread(
            windows.find_windows, params.name, process_for(ctx, params.name)
        )
        if not found and not ctx.index.confident(
            ctx.index.resolve(params.name, {Kind.APP, Kind.GAME})
        ):
            return Prepared(
                "",
                error=ToolResult.fail(f"No veo ninguna ventana de {params.name}", "¿está abierta?"),
            )
        return Prepared(summary=f"Ventana {params.name}")

    async def run(self, params: FocusWindowParams, ctx: ToolContext) -> ToolResult:
        process = process_for(ctx, params.name)
        found = await asyncio.to_thread(windows.find_windows, params.name, process)
        if not found:
            return ToolResult.fail(f"No veo ninguna ventana de {params.name}", "¿está abierta?")
        target = found[0]
        if not await asyncio.to_thread(windows.activate, target.hwnd):
            return ToolResult.fail(f"Windows no me deja traer {target.title} al frente")
        return ToolResult(ok=True, message=f"Ventana {target.title}", data={"hwnd": target.hwnd})
