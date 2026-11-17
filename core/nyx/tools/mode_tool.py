"""mode: entrar o salir de un modo, o decir cuál hay (tarea 8.10). Verde.

«Modo trabajo», «activa el modo noche», «sal del modo privacidad», «¿en qué modo estás?». Lo
que hace cada modo está en `nyx/modes/manager.py` (y docs/MODOS.md).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult


class ModeParams(Params):
    action: Literal["enter", "exit", "status"] = Field(description="enter, exit o status")
    mode: str = Field(default="", max_length=40, description="trabajo, noche, privacidad…")


class ModeTool(Tool[ModeParams]):
    name = "mode"
    description = "Modos de Nyx: entrar (trabajo, noche, privacidad), salir o decir cuál hay."
    risk = Risk.GREEN
    game_policy = GamePolicy.ALLOWED
    category = Category.SYSTEM
    params_model = ModeParams

    async def run(self, params: ModeParams, ctx: ToolContext) -> ToolResult:
        modes = ctx.modes
        if modes is None:
            return ToolResult.fail("Los modos no están disponibles")
        if params.action == "status":
            current = modes.current
            names = ", ".join(m.name for m in modes.all_modes().values())
            if current is None:
                return ToolResult(
                    ok=True, message=f"No estoy en ningún modo. Tengo: {names}.", speak=True
                )
            return ToolResult(ok=True, message=f"Estoy en modo {current.name}.", speak=True)
        if params.action == "exit":
            said = await modes.exit()
            return ToolResult(ok=True, message=f"{said}.", display=said)
        found = modes.find(params.mode)
        if found is None:
            return ToolResult.fail(f"No tengo el modo «{params.mode}»")
        said = await modes.enter(found.id)
        return ToolResult(ok=True, message=f"{said}.", display=said)
