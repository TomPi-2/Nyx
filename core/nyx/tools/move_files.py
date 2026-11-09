"""move_files: mueve archivos a otra carpeta (amarilla, con deshacer)."""

from __future__ import annotations

import asyncio

from nyx.safety.undo import Undo
from nyx.tools.base import Category, GamePolicy, Prepared, Risk, Tool, ToolContext, ToolResult
from nyx.tools.files import describe, unique_target
from nyx.tools.transfer import Plan, TransferParams, move_all, plan, targets


class MoveFiles(Tool[TransferParams]):
    name = "move_files"
    description = (
        "Mueve archivos a otra carpeta. Ej.: «mueve los últimos 5 archivos de Descargas a "
        "Documentos» (folder=Descargas, newest=5, destination=Documentos)."
    )
    risk = Risk.YELLOW
    game_policy = GamePolicy.DEFERRED
    category = Category.FILES
    params_model = TransferParams
    timeout_s = 120.0

    async def prepare(self, params: TransferParams, ctx: ToolContext) -> Prepared:
        return await plan(params, ctx, "Mover")

    async def execute(
        self, params: TransferParams, ctx: ToolContext, prepared: Prepared
    ) -> ToolResult:
        p: Plan = prepared.payload
        pairs = await asyncio.to_thread(targets, p.items, p.destination)
        done = await asyncio.to_thread(move_all, pairs)
        if not done:
            return ToolResult.fail("No he podido mover nada", "¿están abiertos en otro programa?")

        async def undo() -> str:
            back = [(dst, unique_target(src.parent, src.name)) for src, dst in done]
            moved = await asyncio.to_thread(move_all, back)
            return f"Devueltos {len(moved)} a {p.source.name}"

        missing = len(p.items) - len(done)
        text = f"{describe([s for s, _ in done], params.kind)} movidos a {p.destination.name}"
        return ToolResult(
            ok=True,
            message=text + (f" ({missing} no se pudieron)" if missing else ""),
            display=f"Movidos a {p.destination.name}",
            secondary=describe([s for s, _ in done], params.kind).strip("«»"),
            data={"paths": [str(d) for _, d in done]},
            undo=Undo(prepared.summary, undo),
        )
