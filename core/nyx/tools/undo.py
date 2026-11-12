"""undo: deshace la última acción amarilla de los últimos 30 s (verde). «Nyx, deshaz»."""

from __future__ import annotations

import re

from pydantic import Field

from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult

_ENTRY_ID = re.compile(r"[0-9a-f]{12}")


class UndoParams(Params):
    id: str | None = Field(default=None, max_length=40, description="ID (vacío = última)")


class UndoLast(Tool[UndoParams]):
    name = "undo"
    description = "Deshace la última acción. Ej.: «deshaz»."
    risk = Risk.GREEN
    game_policy = GamePolicy.ALLOWED
    category = Category.SYSTEM
    params_model = UndoParams
    timeout_s = 120.0

    async def run(self, params: UndoParams, ctx: ToolContext) -> ToolResult:
        # El botón de la burbuja pasa el ID real (12 hex); si el modelo rellena «la» o similar,
        # se ignora para deshacer la última acción.
        raw_id = params.id.strip() if params.id else None
        entry_id = raw_id if raw_id and _ENTRY_ID.fullmatch(raw_id) else None
        entry = ctx.undo.take(entry_id)
        if entry is None:
            return ToolResult.fail("No hay nada que deshacer", "solo se puede en los primeros 30 s")
        try:
            text = await entry.action()
        except OSError as e:
            return ToolResult.fail(f"No he podido deshacer: {entry.summary}", str(e))
        return ToolResult(ok=True, message=text, display="Deshecho", secondary=text)
