"""copy_files: copia archivos a otra carpeta (amarilla; deshacer = copias a la papelera)."""

from __future__ import annotations

import asyncio

from nyx.safety.undo import Undo
from nyx.tools.base import Category, GamePolicy, Prepared, Risk, Tool, ToolContext, ToolResult
from nyx.tools.delete_files import trash_all
from nyx.tools.files import describe
from nyx.tools.transfer import Plan, TransferParams, copy_all, plan, targets


class CopyFiles(Tool[TransferParams]):
    name = "copy_files"
    description = (
        "Copia archivos a otra carpeta. Ej.: «copia las fotos del Escritorio a Imágenes» "
        "(folder=Escritorio, kind=images, destination=Imágenes); «cópialo al Escritorio» "
        "justo después de encontrar CV.pdf en Documentos (folder=Documentos, names=[CV.pdf], "
        "destination=Escritorio)."
    )
    risk = Risk.YELLOW
    game_policy = GamePolicy.DEFERRED
    category = Category.FILES
    params_model = TransferParams
    timeout_s = 300.0

    async def prepare(self, params: TransferParams, ctx: ToolContext) -> Prepared:
        return await plan(params, ctx, "Copiar")

    async def execute(
        self, params: TransferParams, ctx: ToolContext, prepared: Prepared
    ) -> ToolResult:
        p: Plan = prepared.payload
        pairs = await asyncio.to_thread(targets, p.items, p.destination)
        done = await asyncio.to_thread(copy_all, pairs)
        if not done:
            return ToolResult.fail("No he podido copiar nada")

        async def undo() -> str:
            # Deshacer una copia = mandar las copias a la papelera (nunca borrado definitivo).
            copies = [dst for _, dst in done]
            await asyncio.to_thread(trash_all, copies)
            return f"Copias de {p.destination.name} a la papelera"

        copied = [s for s, _ in done]
        return ToolResult(
            ok=True,
            message=f"{describe(copied, params.kind)} copiados a {p.destination.name}",
            display=f"Copiados a {p.destination.name}",
            secondary=describe(copied, params.kind).strip("«»"),
            data={"paths": [str(d) for _, d in done]},
            undo=Undo(prepared.summary, undo),
        )
