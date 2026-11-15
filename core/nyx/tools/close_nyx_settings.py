"""close_nyx_settings: cierra la ventana de Ajustes de Nyx («cierra tus ajustes»). Verde.

Visto en los registros del 2026-11-15: «cierra tus ajustes» no existía y el modelo contestaba
«vale, te cierro los ajustes» sin hacer nada. Se puede en partida (cerrar no estorba al juego).
"""

from __future__ import annotations

from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult


class CloseNyxSettings(Tool[Params]):
    name = "close_nyx_settings"
    description = "Cierra la ventana de Ajustes de Nyx («cierra tus ajustes»)."
    risk = Risk.GREEN
    game_policy = GamePolicy.ALLOWED
    category = Category.SYSTEM
    params_model = Params

    async def run(self, params: Params, ctx: ToolContext) -> ToolResult:
        if ctx.close_nyx_settings is None:
            return ToolResult.fail("No puedo cerrar los ajustes ahora", "sin interfaz")
        await ctx.close_nyx_settings()
        return ToolResult(ok=True, message="Cerrando los ajustes")
