"""find_files: busca archivos por nombre en las carpetas del usuario (verde).

Motor: Everything si está instalado; si no, el índice de Windows (ver winapi/search.py).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import Field, model_validator

from nyx.index.scanners.folders import known_folders
from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult
from nyx.tools.files import EXTENSIONS, FileKind, preview, resolve_folder
from nyx.winapi import search


class FindFilesParams(Params):
    query: str = Field(default="", max_length=200, description="Parte del nombre del archivo")
    kind: FileKind | None = Field(default=None, description="Solo de este tipo")
    extension: str | None = Field(default=None, max_length=10, description="p. ej. pdf")
    folder: str | None = Field(default=None, max_length=1000, description="Buscar solo aquí")
    limit: int = Field(default=10, ge=1, le=50)

    @model_validator(mode="after")
    def needs_name_or_extension(self) -> FindFilesParams:
        if not self.query.strip() and not self.extension:
            raise ValueError("falta query (parte del nombre) o extension")
        return self

    @property
    def suffix(self) -> str | None:
        return "." + self.extension.lower().lstrip(".") if self.extension else None


def search_roots() -> list[Path]:
    return [p for name, p in known_folders().items() if name != "Carpeta personal"]


class FindFiles(Tool[FindFilesParams]):
    name = "find_files"
    description = (
        "Busca archivos por su nombre. Ej.: «busca la factura de la luz», «busca fotos de "
        "la playa» (kind=images), «busca el contrato en Documentos» (folder=Documentos), "
        "«busca los pdf de Documentos» (extension=pdf, folder=Documentos)."
    )
    risk = Risk.GREEN
    game_policy = GamePolicy.ALLOWED
    category = Category.FILES
    params_model = FindFilesParams
    observe = True
    timeout_s = 15.0

    async def run(self, params: FindFilesParams, ctx: ToolContext) -> ToolResult:
        if params.folder:
            folder = await asyncio.to_thread(resolve_folder, ctx, params.folder)
            if isinstance(folder, ToolResult):
                return folder
            roots = [folder]
        else:
            roots = await asyncio.to_thread(search_roots)
        # «los pdf» sin nombre: se busca por la extensión.
        query = params.query.strip() or params.suffix or ""
        found, engine = await asyncio.to_thread(search.search, query, roots, 50)
        if params.kind:
            found = [p for p in found if p.suffix.lower() in EXTENSIONS[params.kind]]
        if params.suffix:
            found = [p for p in found if p.suffix.lower() == params.suffix]
        found = found[: params.limit]
        if not found:
            return ToolResult.fail(f"No encuentro archivos con «{query}»")
        display = found[0].name if len(found) == 1 else f"{len(found)} resultados"
        secondary = str(found[0].parent) if len(found) == 1 else preview(found)
        return ToolResult(
            ok=True,
            message=f"{len(found)} resultados para «{query}» ({engine})",
            display=display,
            secondary=secondary,
            data={"paths": [str(p) for p in found], "engine": engine},
        )
