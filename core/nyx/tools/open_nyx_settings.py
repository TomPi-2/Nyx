"""open_nyx_settings: abre la ventana de Ajustes de Nyx (verde).

No es la Configuración de Windows (eso es open_settings): «abre tus ajustes», «abre los
ajustes de Nyx», «abre tu configuración del modo partida».
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult

#: Secciones de la ventana (ui/src/settings/Settings.svelte).
Section = Literal["", "apariencia", "activacion", "voz", "respuestas", "partida"]


class OpenNyxSettingsParams(Params):
    section: Section = Field(
        default="",
        description=(
            "Sección: apariencia, activacion (palabra «Nyx»), voz, respuestas o partida "
            "(modo partida). Vacío = la primera"
        ),
    )


class OpenNyxSettings(Tool[OpenNyxSettingsParams]):
    name = "open_nyx_settings"
    description = (
        "Abre los Ajustes de Nyx (los tuyos, no la Configuración de Windows). Ej.: «abre tus "
        "ajustes», «abre los ajustes de Nyx», «tu configuración del modo partida» "
        "(section=partida)."
    )
    risk = Risk.GREEN
    # Como abrir cualquier ventana: con un juego abierto, al terminar la partida.
    game_policy = GamePolicy.DEFERRED
    category = Category.SYSTEM
    params_model = OpenNyxSettingsParams

    async def run(self, params: OpenNyxSettingsParams, ctx: ToolContext) -> ToolResult:
        if ctx.open_nyx_settings is None:
            return ToolResult.fail("No puedo abrir los ajustes ahora", "sin interfaz")
        await ctx.open_nyx_settings(params.section or None)
        return ToolResult(ok=True, message="Abriendo los ajustes")
