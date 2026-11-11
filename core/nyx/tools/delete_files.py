"""delete_files: manda archivos o carpetas a la papelera (roja: siempre se confirma).

Nunca hay borrado permanente (SPEC sección 8): todo va a la papelera de Windows con
send2trash. Durante 30 s se puede deshacer: se recupera de la papelera.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from send2trash import send2trash

from nyx.safety.undo import Undo
from nyx.tools.base import Category, GamePolicy, Prepared, Risk, Tool, ToolContext, ToolResult
from nyx.tools.files import FileSelection, describe, preview, select
from nyx.winapi import recycle

log = logging.getLogger(__name__)

COUNT_LIMIT = 5000


def count_files(items: list[Path]) -> int:
    """Archivos afectados, contando el contenido de las carpetas (para «más de 50 → clic»)."""
    total = 0
    for item in items:
        if item.is_dir():
            for _, _, files in os.walk(item):
                total += len(files)
                if total > COUNT_LIMIT:
                    return total
        else:
            total += 1
    return total


def trash_all(items: list[Path]) -> list[Path]:
    done = []
    for item in items:
        try:
            send2trash(str(item))
            done.append(item)
        except OSError:
            log.warning("No se pudo mandar a la papelera %s", item, exc_info=True)
    return done


class DeleteFiles(Tool[FileSelection]):
    name = "delete_files"
    description = (
        "Manda archivos o carpetas a la papelera. Ej.: «borra Fondos de Imágenes» "
        "(folder=Imágenes, names=[Fondos], include_folders=true)."
    )
    risk = Risk.RED
    game_policy = GamePolicy.DEFERRED
    category = Category.FILES
    params_model = FileSelection
    timeout_s = 120.0

    async def prepare(self, params: FileSelection, ctx: ToolContext) -> Prepared:
        found = await asyncio.to_thread(select, params, ctx)
        if isinstance(found, ToolResult):
            return Prepared("", error=found)
        folder, items = found
        files = await asyncio.to_thread(count_files, items)
        what = describe(items, params.kind)
        extra = f" ({files} archivos)" if any(p.is_dir() for p in items) and files else ""
        return Prepared(
            summary=f"Mandar a la papelera {what}{extra}",
            detail=f"de {folder.name}: {preview(items)}",
            paths=items,
            count=max(files, len(items)),
            payload=items,
        )

    async def execute(
        self, params: FileSelection, ctx: ToolContext, prepared: Prepared
    ) -> ToolResult:
        items: list[Path] = prepared.payload
        done = await asyncio.to_thread(trash_all, items)
        if not done:
            return ToolResult.fail("No he podido mandar nada a la papelera", "¿están abiertos?")
        missing = len(items) - len(done)

        async def undo() -> str:
            back = await asyncio.to_thread(recycle.restore, done)
            if not back:
                raise OSError("no lo encuentro en la papelera")
            return f"Recuperado de la papelera: {describe(back)}"

        return ToolResult(
            ok=True,
            message=f"{describe(done)} en la papelera" + (f" ({missing} no)" if missing else ""),
            display="En la papelera",
            secondary=describe(done, params.kind).strip("«»"),
            data={"paths": [str(p) for p in done]},
            undo=Undo(prepared.summary, undo),
        )
