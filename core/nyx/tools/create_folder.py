"""create_folder: crea una carpeta (verde)."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from pydantic import Field

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
from nyx.tools.files import resolve_folder

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"con", "prn", "aux", "nul"} | {f"{d}{i}" for d in ("com", "lpt") for i in range(1, 10)}


class CreateFolderParams(Params):
    name: str = Field(min_length=1, max_length=200, description="Nombre de la carpeta nueva")
    parent: str = Field(
        default="Documentos", max_length=1000, description="Dónde crearla (Documentos, Escritorio…)"
    )


def valid_name(name: str) -> str | None:
    """El nombre limpio, o None si Windows no lo admite."""
    name = name.strip().rstrip(". ")
    if not name or _INVALID.search(name) or name.lower() in _RESERVED:
        return None
    return name


class CreateFolder(Tool[CreateFolderParams]):
    name = "create_folder"
    description = (
        "Crea una carpeta. Ej.: «crea una carpeta en Documentos llamada Fondos» "
        "(name=Fondos, parent=Documentos)."
    )
    risk = Risk.GREEN
    game_policy = GamePolicy.ALLOWED
    category = Category.FILES
    params_model = CreateFolderParams

    async def prepare(self, params: CreateFolderParams, ctx: ToolContext) -> Prepared:
        name = valid_name(params.name)
        if name is None:
            return Prepared("", error=ToolResult.fail(f"«{params.name}» no vale como nombre"))
        parent = await asyncio.to_thread(resolve_folder, ctx, params.parent)
        if isinstance(parent, ToolResult):
            return Prepared("", error=parent)
        target = parent / name
        if await asyncio.to_thread(target.exists):
            return Prepared(
                "", error=ToolResult.fail(f"Ya existe {name} en {parent.name}", "elige otro nombre")
            )
        return Prepared(
            f"Crear la carpeta {name} en {parent.name}", targets=[target], payload=target
        )

    async def execute(
        self, params: CreateFolderParams, ctx: ToolContext, prepared: Prepared
    ) -> ToolResult:
        target: Path = prepared.payload
        try:
            await asyncio.to_thread(target.mkdir, parents=False, exist_ok=False)
        except OSError as e:
            return ToolResult.fail(f"No he podido crear {target.name}", str(e))
        return ToolResult(
            ok=True,
            message=f"Carpeta {target.name} creada en {target.parent.name}",
            display=f"Carpeta {target.name}",
            secondary=f"creada en {target.parent.name}",
            data={"path": str(target)},
        )
