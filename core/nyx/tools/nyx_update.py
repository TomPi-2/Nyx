"""nyx_update: «Nyx, actualízate» (verde, tarea 9.06).

Con una versión nueva ya descargada (la app la baja sola), la aplica: Nyx se reinicia unos
segundos con la versión nueva. Si no hay ninguna, lo dice. Es lo que hace el botón
[Actualizar] del aviso en el modo «Solo avisar» (Ajustes → General), pero hablando.

Solo la usa el router (`llm_visible = False`): no cambia las herramientas que ve el modelo
entrenado.
"""

from __future__ import annotations

from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult


class NyxUpdateParams(Params):
    pass


class NyxUpdate(Tool[NyxUpdateParams]):
    name = "nyx_update"
    description = "Aplica la versión nueva de Nyx ya descargada (se reinicia unos segundos)."
    risk = Risk.GREEN
    # Reiniciarse en mitad de una partida, no: al terminar.
    game_policy = GamePolicy.DEFERRED
    category = Category.SYSTEM
    params_model = NyxUpdateParams
    llm_visible = False

    async def run(self, params: NyxUpdateParams, ctx: ToolContext) -> ToolResult:
        if ctx.update_now is None:
            return ToolResult.fail("Ahora no puedo actualizarme")
        said = await ctx.update_now()
        return ToolResult(ok=True, message=said, speak=True, observe=False)
