"""dictation: «escribe lo que te diga» (tarea 8.04). Amarilla (escribe en otra app).

Empieza el dictado en la ventana en la que estabas (o en la app que se diga) y el pipeline
escribe lo que oye hasta «ya está» o 20 s sin hablar (`nyx/dictation.py`). Nunca en juegos, en
partida, en Nyx ni en terminales (lo dictado serían órdenes).
"""

from __future__ import annotations

import asyncio
from typing import Literal

from pydantic import Field

from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult
from nyx.winapi import games, windows


class DictationParams(Params):
    action: Literal["start", "stop"] = Field(default="start", description="start o stop")
    app: str | None = Field(default=None, max_length=100, description="App (vacío = la activa)")


class DictationTool(Tool[DictationParams]):
    name = "dictation"
    description = "Dictado: escribe en la app lo que el usuario vaya diciendo hasta «ya está»."
    risk = Risk.YELLOW
    game_policy = GamePolicy.BLOCKED
    category = Category.WINDOWS
    params_model = DictationParams

    async def run(self, params: DictationParams, ctx: ToolContext) -> ToolResult:
        from nyx.tools.app_action import game_processes
        from nyx.tools.focus_window import find_target_windows
        from nyx.tools.type_text import _NOT_TARGETS, _TERMINALS

        dictation = ctx.dictation
        if dictation is None:
            return ToolResult.fail("El dictado necesita el micrófono")
        if params.action == "stop":
            dictation.stop()
            return ToolResult(ok=True, message="Dictado terminado.")
        if params.app:
            found = await asyncio.to_thread(find_target_windows, ctx, params.app)
        else:
            listed = await asyncio.to_thread(windows.list_windows)
            found = [w for w in listed if w.process not in _NOT_TARGETS][:1]
        target = next((w for w in found if w.process not in _NOT_TARGETS), None)
        if target is None:
            where = params.app or "ninguna app"
            return ToolResult.fail(f"No veo {where} para escribir", "abre donde quieres escribir")
        if target.process.lower() in _TERMINALS:
            return ToolResult.fail("En una terminal no dicto: lo escrito serían órdenes")
        is_game = await asyncio.to_thread(
            games.window_is_game, target.hwnd, target.process, game_processes(ctx)
        )
        if is_game:
            return ToolResult.fail("Dentro de los juegos no escribo")
        dictation.start(target.hwnd, target.title)
        return ToolResult(
            ok=True,
            message=f"Te escucho: escribo en {target.title}. Di «ya está» para terminar.",
            display="Dictando",
            secondary=f"en {target.title} · di «ya está» para terminar",
            speak=True,
        )
