"""recent_files: los documentos abiertos hace poco (tarea 8.06). Verde; abrir, al terminar la
partida (como `open_path`).

«Abre el último Word», «¿qué documentos he abierto hoy?», «¿cuál fue el último Excel que
abrí?». Sale de la carpeta Recientes de Windows (`winapi/recent.py`), sin indexar nada.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Literal

from pydantic import Field

from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult
from nyx.tools.list_items import spoken_join
from nyx.winapi import focus, launch
from nyx.winapi.recent import Kind, Recent, recent_files

LABELS: dict[str, tuple[str, str]] = {  # (uno, varios)
    "any": ("documento", "documentos"),
    "word": ("Word", "Word"),
    "excel": ("Excel", "Excel"),
    "powerpoint": ("PowerPoint", "PowerPoint"),
    "pdf": ("PDF", "PDF"),
    "image": ("imagen", "imágenes"),
    "video": ("vídeo", "vídeos"),
    "text": ("archivo de texto", "archivos de texto"),
}


class RecentFilesParams(Params):
    action: Literal["open", "list"] = Field(description="open (el último) o list")
    kind: Kind = Field(
        default="any", description="any, word, excel, powerpoint, pdf, image, video, text"
    )
    count: int = Field(default=5, ge=1, le=10, description="Cuántos (list)")


class RecentFiles(Tool[RecentFilesParams]):
    name = "recent_files"
    description = (
        "Documentos abiertos hace poco: abrir el último o decir cuáles. Ej.: «abre el último Word»."
    )
    risk = Risk.GREEN
    game_policy = GamePolicy.DEFERRED
    category = Category.FILES
    params_model = RecentFilesParams
    observe = True

    def __init__(self, reader: Callable[[Kind, int], list[Recent]] | None = None) -> None:
        self._read = reader or (lambda kind, limit: recent_files(kind, limit))

    async def run(self, params: RecentFilesParams, ctx: ToolContext) -> ToolResult:
        one, many = LABELS[params.kind]
        limit = 1 if params.action == "open" else params.count
        found = await asyncio.to_thread(self._read, params.kind, limit)
        if not found:
            return ToolResult.fail(f"No encuentro ningún {one} abierto hace poco")
        if params.action == "open":
            item = found[0]
            try:
                before = await asyncio.to_thread(focus.snapshot)
                await asyncio.to_thread(launch.shell_open, str(item.path))
            except OSError as e:
                return ToolResult.fail(f"No he podido abrir {item.path.name}", str(e))
            focus.request(item.path.stem, None, before)
            return ToolResult(
                ok=True,
                message=f"Abriendo {item.path.name}",
                data={"path": str(item.path)},
            )
        now = datetime.now()
        parts = [f"{r.path.name} ({_when(r.opened, now)})" for r in found]
        return ToolResult(
            ok=True,
            message=f"Los últimos {many} que has abierto: {spoken_join(parts)}.",
            display=f"Últimos {many}",
            secondary=", ".join(r.path.name for r in found)[:300],
            speak=True,
        )


def _when(moment: datetime, now: datetime) -> str:
    days = (now.date() - moment.date()).days
    if days == 0:
        return f"hoy a las {moment:%H:%M}"
    if days == 1:
        return "ayer"
    return f"el {moment:%d/%m}"
