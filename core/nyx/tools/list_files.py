"""list_files: lista archivos de una carpeta con filtros (verde). Sirve también de primer paso
en los planes del LLM («mueve los últimos 5 de Descargas…»)."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from nyx.tools.base import Category, GamePolicy, Risk, Tool, ToolContext, ToolResult
from nyx.tools.files import FileSelection, describe, preview, select

DEFAULT_NEWEST = 10


def count_entries(folder: Path) -> tuple[int, int]:
    """(archivos, carpetas) del primer nivel, sin los ocultos ni los del sistema."""
    files = folders = 0
    with os.scandir(folder) as entries:
        for e in entries:
            if e.name.startswith((".", "~$")) or e.name.lower() == "desktop.ini":
                continue
            try:
                if e.is_dir():
                    folders += 1
                elif e.is_file():
                    files += 1
            except OSError:
                continue
    return files, folders


def folder_label(asked: str, folder: Path) -> str:
    """Como la dijo el usuario («descargas» → «Descargas»), no «Downloads»."""
    if Path(asked).is_absolute():
        return folder.name
    return asked[:1].upper() + asked[1:]


def plural(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


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
        overview = not (
            params.names or params.newest or params.kind or params.extension or params.all
        )
        if overview:
            params = params.model_copy(update={"newest": DEFAULT_NEWEST})
        found = await asyncio.to_thread(select, params, ctx)
        if isinstance(found, ToolResult):
            return found
        folder, items = found
        if overview:
            # «¿Qué hay en Descargas?»: el total de verdad y los más recientes (antes decía
            # «10 archivos» con cientos dentro; ERRORES.md, 2026-11-11).
            files, folders = await asyncio.to_thread(count_entries, folder)
            label = folder_label(params.folder, folder)
            recent = f"los {len(items)} más recientes" if len(items) > 1 else "el más reciente"
            also = f" y {plural(folders, 'carpeta')}" if folders else ""
            return ToolResult(
                ok=True,
                message=f"En {label} hay {plural(files, 'archivo')}{also}; {recent}",
                display=plural(files, "archivo"),
                secondary=f"{also.strip()} en {label}" if folders else preview(items),
                data={"folder": str(folder), "paths": [str(p) for p in items]},
            )
        return ToolResult(
            ok=True,
            message=f"{describe(items, params.kind)} en {folder.name}",
            display=describe(items, params.kind).strip("«»"),
            secondary=preview(items),
            data={"folder": str(folder), "paths": [str(p) for p in items]},
        )
