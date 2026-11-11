"""pending: ver y cancelar lo que Nyx dejó para después de la partida (verde).

«¿Qué tienes pendiente?», «olvida lo de los ajustes», «no hagas nada de lo pendiente».
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from nyx.executor import describe_call
from nyx.index.aliases import normalize
from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult


class PendingParams(Params):
    action: Literal["list", "cancel"] = Field(default="list", description="Ver o cancelar")
    which: str = Field(default="", max_length=100, description="Qué cancelar (vacío = todo)")


def _pick(summaries: list[str], which: str) -> int | None:
    """Posición de lo que se pide quitar; None si no se reconoce."""
    if which.isdigit():
        n = int(which) - 1
        return n if 0 <= n < len(summaries) else None
    words = normalize(which).split()
    for i, summary in enumerate(summaries):
        text = normalize(summary)
        if words and all(w in text for w in words):
            return i
    return None


class Pending(Tool[PendingParams]):
    name = "pending"
    description = (
        "Ve o cancela lo diferido de la partida. Ej.: «¿qué tienes pendiente?» (action=list)."
    )
    risk = Risk.GREEN
    game_policy = GamePolicy.ALLOWED
    category = Category.SYSTEM
    params_model = PendingParams

    async def run(self, params: PendingParams, ctx: ToolContext) -> ToolResult:
        gate = ctx.game
        queue = gate.queue if gate is not None else []
        if not queue:
            return ToolResult(ok=True, message="No tengo nada pendiente", display="Nada pendiente")
        assert gate is not None
        summaries = [item.summary or describe_call(item.call) for item in queue]
        if params.action == "list":
            listed = "; ".join(f"{i}. {s}" for i, s in enumerate(summaries, 1))
            return ToolResult(
                ok=True,
                message=f"Al terminar la partida: {listed}",
                display="Pendiente",
                secondary=listed,
            )
        if not params.which.strip():
            gate.cancel()
            return ToolResult(ok=True, message="Vale, no haré nada de lo pendiente")
        index = _pick(summaries, params.which)
        if index is None:
            return ToolResult.fail(f"No tengo pendiente «{params.which}»", "; ".join(summaries))
        gone = gate.cancel(index)
        return ToolResult(ok=True, message=f"Vale, ya no haré: {gone[0].summary}")
