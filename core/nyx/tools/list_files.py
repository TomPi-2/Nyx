"""list_files: lista archivos de una carpeta con filtros (verde). Sirve también de primer paso
en los planes del LLM («mueve los últimos 5 de Descargas…»)."""

from __future__ import annotations

import asyncio

from nyx.tools.base import Category, GamePolicy, Risk, Tool, ToolContext, ToolResult
from nyx.tools.files import FileSelection, describe, preview, select

DEFAULT_NEWEST = 10


class ListFiles(Tool[FileSelection]):
    name = "list_files"
    description = (
        "Lista los archivos de una carpeta. Ej.: «qué hay en Descargas», «los últimos 5 "
        "archivos de Descargas» (newest=5), «las imágenes del Escritorio» (kind=images)."
    )
    risk = Risk.GREEN
    game_policy = GamePolicy.ALLOWED
    category = Category.FILES
    params_model = FileSelection
    observe = True

    async def run(self, params: FileSelection, ctx: ToolContext) -> ToolResult:
        if not (params.names or params.newest or params.kind or params.extension or params.all):
            params = params.model_copy(update={"newest": DEFAULT_NEWEST})
        found = await asyncio.to_thread(select, params, ctx)
        if isinstance(found, ToolResult):
            return found
        folder, items = found
        return ToolResult(
            ok=True,
            message=f"{describe(items, params.kind)} en {folder.name}",
            display=describe(items, params.kind).strip("«»"),
            secondary=preview(items),
            data={"folder": str(folder), "paths": [str(p) for p in items]},
        )
