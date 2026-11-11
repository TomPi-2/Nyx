"""open_settings: abre una página de Configuración de Windows (verde)."""

from __future__ import annotations

import asyncio

from pydantic import Field

from nyx.index.model import Kind
from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult
from nyx.tools.resolve import pick
from nyx.winapi import focus, launch


class OpenSettingsParams(Params):
    page: str = Field(default="", max_length=100, description="Página (sonido, wifi, ratón…)")
    focus: bool = Field(default=True, description="Traer al frente")


class OpenSettings(Tool[OpenSettingsParams]):
    name = "open_settings"
    description = "Abre la Configuración de Windows. Ej.: «ajustes de sonido» (page=sonido)."
    risk = Risk.GREEN
    game_policy = GamePolicy.DEFERRED
    category = Category.SYSTEM
    params_model = OpenSettingsParams

    async def run(self, params: OpenSettingsParams, ctx: ToolContext) -> ToolResult:
        found = pick(ctx.index, params.page or "configuracion", {Kind.SETTING}, "la página")
        if isinstance(found, ToolResult):
            return found
        entry = found.entry
        try:
            before = await asyncio.to_thread(focus.snapshot) if params.focus else set()
            await asyncio.to_thread(launch.shell_open, entry.launch.value)
        except OSError as e:
            return ToolResult.fail(f"No he podido abrir {entry.name}", str(e))
        ctx.index.record_use(entry.key)
        if params.focus:
            # La ventana de Configuración se llama así sea cual sea la página.
            focus.request("Configuración", None, before, reuse_after_s=1.0)
        return ToolResult(ok=True, message=f"Abriendo {entry.name}")
