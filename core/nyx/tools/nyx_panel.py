"""nyx_panel: saca junto a Nyx el panel de su color, su tamaño o el color de los paneles (verde,
tarea 9.11).

«Quiero cambiarte el color», «cambia el color de los paneles», «quiero cambiar tu tamaño»: en
vez de abrir Ajustes, el mismo panel del primer arranque (setup/flow.py, modo suelto) debajo
de Nyx. Ahí se elige hablando («coral», «más grande») o tocando, y «listo» lo cierra. Lo que
ya dice qué poner («ponte coral», «hazte más grande») lo hace nyx_control directamente.

Solo la usa el router (`llm_visible = False`): así no cambian las herramientas que ve el
modelo entrenado (6.27). Si más adelante el modelo debe sacarla, entra en la ronda 4.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult

Panel = Literal["color", "tamaño", "paneles"]

#: Modo del flujo guiado (GuidedSetup.start) para cada panel.
MODES: dict[str, Literal["color", "size", "tint"]] = {
    "color": "color",
    "tamaño": "size",
    "paneles": "tint",
}


class NyxPanelParams(Params):
    panel: Panel = Field(description="Qué panel: su color, su tamaño o el color de los paneles")


class NyxPanel(Tool[NyxPanelParams]):
    name = "nyx_panel"
    description = (
        "Saca junto a Nyx el panel para elegir su color, su tamaño o el color de los paneles."
    )
    risk = Risk.GREEN
    # Como abrir una ventana: con un juego abierto, al terminar la partida.
    game_policy = GamePolicy.DEFERRED
    category = Category.SYSTEM
    params_model = NyxPanelParams
    llm_visible = False

    async def run(self, params: NyxPanelParams, ctx: ToolContext) -> ToolResult:
        if ctx.open_nyx_panel is None:
            return ToolResult.fail("No puedo sacar el panel ahora", "sin interfaz")
        await ctx.open_nyx_panel(MODES[params.panel])
        # En silencio: lo dice Nyx desde el panel («¿De qué color me quieres?»).
        return ToolResult(ok=True, message=f"Panel de {params.panel}", observe=False)
