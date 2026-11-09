"""rename_file: renombra un archivo o carpeta (amarilla, con deshacer)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from pydantic import Field

from nyx.safety.undo import Undo
from nyx.tools.base import (
    Category,
    GamePolicy,
    Params,
    Prepared,
    Risk,
    Tool,
    ToolContext,
    ToolResult,
)
from nyx.tools.create_folder import valid_name
from nyx.tools.files import FileSelection, select


class RenameParams(Params):
    folder: str = Field(min_length=1, max_length=1000, description="Carpeta donde está")
    name: str = Field(min_length=1, max_length=255, description="Nombre actual (o parte)")
    new_name: str = Field(min_length=1, max_length=255, description="Nombre nuevo")


@dataclass(frozen=True, slots=True)
class Rename:
    src: Path
    dst: Path


def _new_path(src: Path, new_name: str) -> Path:
    # «renombra informe.pdf a final» → final.pdf (se conserva la extensión si no se dice).
    if src.is_file() and src.suffix and not Path(new_name).suffix:
        new_name += src.suffix
    return src.with_name(new_name)


class RenameFile(Tool[RenameParams]):
    name = "rename_file"
    description = (
        "Cambia el nombre de un archivo o carpeta. Ej.: «renombra informe de Descargas a "
        "informe final» (folder=Descargas, name=informe, new_name=informe final)."
    )
    risk = Risk.YELLOW
    game_policy = GamePolicy.DEFERRED
    category = Category.FILES
    params_model = RenameParams

    async def prepare(self, params: RenameParams, ctx: ToolContext) -> Prepared:
        new_name = valid_name(params.new_name)
        if new_name is None:
            return Prepared("", error=ToolResult.fail(f"«{params.new_name}» no vale como nombre"))
        selection = FileSelection(folder=params.folder, names=[params.name], include_folders=True)
        found = await asyncio.to_thread(select, selection, ctx)
        if isinstance(found, ToolResult):
            return Prepared("", error=found)
        _, items = found
        if len(items) > 1:
            names = ", ".join(p.name for p in items[:3])
            return Prepared("", error=ToolResult.fail(f"Hay varios: {names}", "dime cuál"))
        src = items[0]
        dst = _new_path(src, new_name)
        if await asyncio.to_thread(dst.exists):
            return Prepared("", error=ToolResult.fail(f"Ya existe {dst.name}"))
        return Prepared(
            summary=f"Renombrar «{src.name}» a «{dst.name}»",
            paths=[src],
            targets=[dst],
            count=1,
            payload=Rename(src, dst),
        )

    async def execute(
        self, params: RenameParams, ctx: ToolContext, prepared: Prepared
    ) -> ToolResult:
        r: Rename = prepared.payload
        try:
            await asyncio.to_thread(r.src.rename, r.dst)
        except OSError as e:
            return ToolResult.fail(f"No he podido renombrar {r.src.name}", str(e))

        async def undo() -> str:
            await asyncio.to_thread(r.dst.rename, r.src)
            return f"Vuelve a llamarse {r.src.name}"

        return ToolResult(
            ok=True,
            message=f"«{r.src.name}» ahora es «{r.dst.name}»",
            display=r.dst.name,
            secondary=f"antes {r.src.name}",
            data={"path": str(r.dst)},
            undo=Undo(prepared.summary, undo),
        )
