"""open_path: abre una carpeta (o un archivo con su app predeterminada) (verde)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import Field

from nyx.index.model import Kind
from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult
from nyx.tools.resolve import pick
from nyx.winapi import focus, launch


class OpenPathParams(Params):
    target: str = Field(min_length=1, max_length=1000, description="Carpeta o ruta")
    focus: bool = Field(default=True, description="Traer al frente")


class OpenPath(Tool[OpenPathParams]):
    name = "open_path"
    description = "Abre una carpeta o archivo. Ej.: «abre Descargas» (target=Descargas)."
    risk = Risk.GREEN
    game_policy = GamePolicy.DEFERRED
    category = Category.FILES
    params_model = OpenPathParams

    async def run(self, params: OpenPathParams, ctx: ToolContext) -> ToolResult:
        path = Path(params.target)
        if path.is_absolute():
            if not await asyncio.to_thread(path.exists):
                return ToolResult.fail(f"No existe {path}")
            name = path.name or str(path)
            key = None
        else:
            found = pick(ctx.index, params.target, {Kind.FOLDER}, "la carpeta")
            if isinstance(found, ToolResult):
                return found
            path, name, key = Path(found.entry.launch.value), found.entry.name, found.entry.key
            if not await asyncio.to_thread(path.exists):
                return ToolResult.fail(f"La carpeta {name} ya no existe")
        try:
            before = await asyncio.to_thread(focus.snapshot) if params.focus else set()
            await asyncio.to_thread(launch.shell_open, str(path))
        except OSError as e:
            return ToolResult.fail(f"No he podido abrir {name}", str(e))
        if key:
            ctx.index.record_use(key)
        if params.focus:
            # Por el título: todas las carpetas son del mismo proceso (explorer.exe).
            focus.request(name, None, before)
        return ToolResult(ok=True, message=f"Abriendo {name}", data={"path": str(path)})
