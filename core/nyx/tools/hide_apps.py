"""hide_apps: ocultar del todo las ventanas de una app y volver a enseñarlas (tarea 8.08).

«Oculta Discord del todo», «esconde WhatsApp de la barra», «enséñalas», «vuelve a mostrar
Discord». La app sigue abierta; sus ventanas no se ven ni en la barra de tareas ni en Alt+Tab
hasta que se piden (o al cerrar o arrancar Nyx: `winapi/hidden.py`). «Oculta Discord» a secas
sigue siendo minimizar (`window_layout`). Nunca juegos ni Nyx. Amarilla, con deshacer.
"""

from __future__ import annotations

import asyncio
from typing import Literal

from pydantic import Field

from nyx.safety.undo import Undo
from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult
from nyx.tools.focus_window import find_target_windows
from nyx.winapi import games
from nyx.winapi.hidden import HiddenWindow, HiddenWindows

_NYX = frozenset({"nyx-ui.exe", "nyx.exe", "python.exe", "pythonw.exe"})


class HideAppsParams(Params):
    action: Literal["hide", "show"] = Field(description="hide (ocultar) o show (enseñar)")
    app: str | None = Field(default=None, max_length=100, description="App (show: vacío = todas)")


class HideApps(Tool[HideAppsParams]):
    name = "hide_apps"
    description = "Oculta del todo una app (ni en la barra) o vuelve a enseñar las ocultas."
    risk = Risk.YELLOW
    game_policy = GamePolicy.DEFERRED
    category = Category.WINDOWS
    params_model = HideAppsParams

    def __init__(self, store: HiddenWindows | None = None) -> None:
        self._store = store

    @property
    def store(self) -> HiddenWindows:
        if self._store is None:
            self._store = HiddenWindows()
        return self._store

    async def run(self, params: HideAppsParams, ctx: ToolContext) -> ToolResult:
        if params.action == "show":
            return await self._show(params.app, ctx)
        if not params.app:
            return ToolResult.fail("¿Qué app oculto?")
        found = await asyncio.to_thread(find_target_windows, ctx, params.app)
        found = [w for w in found if w.process.lower() not in _NYX]
        if not found:
            return ToolResult.fail(f"No veo ninguna ventana de {params.app}", "¿está abierta?")
        from nyx.tools.app_action import game_processes

        for w in found:
            if await asyncio.to_thread(
                games.window_is_game, w.hwnd, w.process, game_processes(ctx)
            ):
                return ToolResult.fail("Los juegos no los oculto")
        hidden = await asyncio.to_thread(
            self.store.hide, [HiddenWindow(w.hwnd, w.process, w.title) for w in found]
        )
        if not hidden:
            return ToolResult.fail(f"Windows no me deja ocultar {params.app}")
        process = hidden[0].process

        async def back() -> str:
            await asyncio.to_thread(self.store.show, process)
            return f"{params.app} otra vez a la vista"

        return ToolResult(
            ok=True,
            message=f"He ocultado {params.app}. Sigue abierto: dime «enséñalo» para que vuelva.",
            display=f"{params.app} oculto",
            secondary="sigue abierto · «enséñalo» para verlo",
            undo=Undo(f"Ocultar {params.app}", back),
        )

    async def _show(self, app: str | None, ctx: ToolContext) -> ToolResult:
        hidden = await asyncio.to_thread(self.store.hidden)
        process: str | None = None
        if app:
            from nyx.tools.focus_window import process_for

            process = await asyncio.to_thread(process_for, ctx, app)
            wanted = app.lower()
            match = [
                w
                for w in hidden
                if w.process == process or wanted in w.title.lower() or wanted in w.process
            ]
            if not match:
                return ToolResult.fail(f"No tengo {app} oculto")
            process = match[0].process
        elif not hidden:
            return ToolResult(ok=True, message="No tengo nada oculto.", speak=True)
        back = await asyncio.to_thread(self.store.show, process)
        names = sorted({w.title.split(" - ")[-1] for w in back})
        what = ", ".join(names[:4]) if names else "lo oculto"
        return ToolResult(ok=True, message=f"Otra vez a la vista: {what}.")


def restore_hidden() -> int:
    """Al arrancar y al cerrar Nyx: nada se queda oculto sin Nyx para devolverlo."""
    try:
        return len(HiddenWindows().show())
    except Exception:
        return 0
