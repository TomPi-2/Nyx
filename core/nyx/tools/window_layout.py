"""window_layout: maximizar, minimizar, restaurar, media pantalla u otro monitor (verde)."""

from __future__ import annotations

import asyncio
from typing import Literal

from pydantic import Field

from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult
from nyx.tools.focus_window import process_for
from nyx.winapi import windows

Action = Literal["maximize", "minimize", "restore", "left", "right", "next_monitor"]


class WindowLayoutParams(Params):
    action: Action = Field(description="Qué hacer con la ventana")
    name: str | None = Field(
        default=None, max_length=100, description="App o ventana; vacío = la ventana activa"
    )


def apply(hwnd: int, action: Action) -> None:
    if action in ("maximize", "minimize", "restore"):
        windows.show(hwnd, action)
        return
    screens = windows.monitors()
    current = windows.window_rect(hwnd)
    i = windows.monitor_of(current, screens)
    if action in ("left", "right"):
        windows.place(hwnd, windows.half(screens[i].work, action))
        return
    if len(screens) < 2:
        raise ValueError("solo hay un monitor")
    dst = screens[(i + 1) % len(screens)]
    maximized = windows.is_maximized(hwnd)
    if maximized:
        windows.show(hwnd, "restore")
        current = windows.window_rect(hwnd)
    windows.place(hwnd, windows.translate(current, screens[i].work, dst.work))
    if maximized:
        windows.show(hwnd, "maximize")


class WindowLayout(Tool[WindowLayoutParams]):
    name = "window_layout"
    description = (
        "Coloca una ventana: maximizar, minimizar, restaurar, a la mitad izquierda o derecha, "
        "o al otro monitor. Ej.: «maximiza Chrome», «pon esta ventana a la izquierda», "
        "«mueve Discord al otro monitor»."
    )
    risk = Risk.GREEN
    game_policy = GamePolicy.DEFERRED
    category = Category.WINDOWS
    params_model = WindowLayoutParams

    async def run(self, params: WindowLayoutParams, ctx: ToolContext) -> ToolResult:
        if params.name:
            process = process_for(ctx, params.name)
            found = await asyncio.to_thread(windows.find_windows, params.name, process)
            if not found:
                return ToolResult.fail(f"No veo ninguna ventana de {params.name}")
            target = found[0]
        else:
            fg = await asyncio.to_thread(windows.foreground)
            if fg is None:
                return ToolResult.fail("No hay ninguna ventana activa")
            target = fg
        try:
            await asyncio.to_thread(apply, target.hwnd, params.action)
        except ValueError as e:
            return ToolResult.fail(f"No puedo: {e}")
        return ToolResult(ok=True, message=f"{target.title}: {params.action}")
