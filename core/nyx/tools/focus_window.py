"""focus_window: trae al frente la ventana de una app abierta (verde)."""

from __future__ import annotations

import asyncio

from pydantic import Field

from nyx.index.aliases import normalize, strip_articles
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
from nyx.winapi import focus, windows
from nyx.winapi.windows import Window

_OPERA_NAMES = frozenset({"opera", "opera gx", "operaje x", "opera g x", "operagx"})
_BROWSER_NAMES = frozenset({"navegador", "browser"})
_BROWSER_PROCESSES = frozenset(
    {
        "chrome.exe",
        "msedge.exe",
        "firefox.exe",
        "opera.exe",
        "opera_gx.exe",
        "brave.exe",
        "vivaldi.exe",
    }
)


class FocusWindowParams(Params):
    name: str = Field(min_length=1, max_length=100, description="App o título")


def process_for(ctx: ToolContext, name: str) -> str | None:
    """Ejecutable de la app con ese nombre, si la caché lo sabe (más fiable que el título)."""
    clean = strip_articles(normalize(name))
    if clean in _BROWSER_NAMES:
        return focus.default_browser_process()
    for query in (name, clean):
        if query:
            best = ctx.index.confident(ctx.index.resolve(query, {Kind.APP, Kind.GAME}))
            if best and best.entry.process:
                proc = best.entry.process
                if proc == "launcher.exe" and "opera" in normalize(best.entry.name):
                    return "opera.exe"
                return proc
    if clean in _OPERA_NAMES:
        return "opera.exe"
    return None


def find_target_windows(ctx: ToolContext, name: str) -> list[Window]:
    """Busca ventanas por nombre/alias/ejecutable (incluye «el navegador» y variantes de Opera)."""
    clean = strip_articles(normalize(name))
    process = process_for(ctx, name)
    found = windows.find_windows(clean or name, process)
    if not found and clean in _OPERA_NAMES:
        for exe in ("opera.exe", "opera_gx.exe"):
            found = windows.find_windows("opera", exe)
            if found:
                break
    if not found and clean in _BROWSER_NAMES and process is None:
        found = [w for w in windows.list_windows() if w.process in _BROWSER_PROCESSES]
    return found


class FocusWindow(Tool[FocusWindowParams]):
    name = "focus_window"
    description = "Trae al frente una ventana abierta. Ej.: «cambia a Chrome» (name=Chrome)."
    risk = Risk.GREEN
    game_policy = GamePolicy.DEFERRED
    category = Category.WINDOWS
    params_model = FocusWindowParams

    async def prepare(self, params: FocusWindowParams, ctx: ToolContext) -> Prepared:
        """Si no hay ninguna ventana así, se dice ya (también en partida, antes de diferirlo)."""
        found = await asyncio.to_thread(find_target_windows, ctx, params.name)
        if not found and not ctx.index.confident(
            ctx.index.resolve(params.name, {Kind.APP, Kind.GAME})
        ):
            return Prepared(
                "",
                error=ToolResult.fail(f"No veo ninguna ventana de {params.name}", "¿está abierta?"),
            )
        return Prepared(summary=f"Ventana {params.name}")

    async def run(self, params: FocusWindowParams, ctx: ToolContext) -> ToolResult:
        found = await asyncio.to_thread(find_target_windows, ctx, params.name)
        if not found:
            return ToolResult.fail(f"No veo ninguna ventana de {params.name}", "¿está abierta?")
        target = found[0]
        if not await asyncio.to_thread(windows.activate, target.hwnd):
            return ToolResult.fail(f"Windows no me deja traer {target.title} al frente")
        return ToolResult(ok=True, message=f"Ventana {target.title}", data={"hwnd": target.hwnd})
