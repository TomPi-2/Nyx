"""open_app: abre una app o un juego de la caché (verde)."""

from __future__ import annotations

import asyncio

from pydantic import Field

from nyx.index.model import Kind
from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult
from nyx.tools.resolve import pick
from nyx.winapi import focus, launch


class OpenAppParams(Params):
    name: str = Field(min_length=1, max_length=100, description="Nombre de la app")
    focus: bool = Field(default=True, description="Traer al frente")


class OpenApp(Tool[OpenAppParams]):
    name = "open_app"
    description = "Abre una app o juego instalado. Ej.: «abre Spotify» (name=Spotify)."
    risk = Risk.GREEN
    game_policy = GamePolicy.DEFERRED
    category = Category.APPS
    params_model = OpenAppParams

    async def run(self, params: OpenAppParams, ctx: ToolContext) -> ToolResult:
        found = pick(ctx.index, params.name, {Kind.APP, Kind.GAME}, "la app")
        if isinstance(found, ToolResult):
            return found
        entry = found.entry
        try:
            before = await asyncio.to_thread(focus.snapshot) if params.focus else set()
            await asyncio.to_thread(launch.launch, entry.launch)
        except OSError as e:
            return ToolResult.fail(f"No he podido abrir {entry.name}", str(e))
        ctx.index.record_use(entry.key)
        if params.focus:
            focus.request(entry.name, entry.process, before)
        return ToolResult(ok=True, message=f"Abriendo {entry.name}", data={"key": entry.key})
