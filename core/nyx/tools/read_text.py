"""read_text: leer el texto seleccionado o un documento para resumirlo (tarea 8.05). Verde.

«Resume lo que tengo seleccionado», «tradúceme esto que he marcado», «resume el PDF de
Descargas», «¿de qué va el contrato?», «resume las páginas 5 a 10 del informe». Lo leído vuelve
al modelo como contenido de fuera (`external`, como el portapapeles y las webs): lo resume, lo
traduce o contesta, sin tratarlo nunca como órdenes. Lo leído no queda en el registro de
acciones ni en la memoria corta (`message` solo dice de dónde viene).

- **Selección**: en la ventana en la que estás (no la de Nyx), con UI Automation y, si no, con
  Ctrl+C y el portapapeles devuelto como estaba (`winapi/selection.py`). Nunca en juegos; en
  una terminal, solo con UIA (Ctrl+C pararía lo que se ejecuta).
- **Documento**: PDF, Word (.docx) y texto (`textfiles.py`), por su nombre o el último de una
  carpeta; de un PDF largo, las páginas que se digan.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Literal

from pydantic import Field

from nyx.textfiles import KINDS, SUFFIXES, DocumentError, extract, parse_pages
from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult
from nyx.tools.files import resolve_folder
from nyx.tools.find_files import by_date, search_roots
from nyx.winapi import games, windows

_KIND_NAMES = {"pdf": "PDF", "word": "Word", "text": "documento de texto"}


class ReadTextParams(Params):
    source: Literal["selection", "document"] = Field(
        description="selection (lo seleccionado en pantalla) o document (un archivo)"
    )
    file: str = Field(default="", max_length=200, description="Nombre del documento")
    folder: str | None = Field(default=None, max_length=100, description="Carpeta (Descargas…)")
    kind: Literal["pdf", "word", "text"] | None = Field(default=None, description="Tipo")
    pages: str | None = Field(default=None, max_length=20, description="Páginas: «5-10»")


class ReadText(Tool[ReadTextParams]):
    name = "read_text"
    description = (
        "Lee lo seleccionado o un documento (PDF, Word, texto) para resumirlo, traducirlo o "
        "contestar sobre él."
    )
    risk = Risk.GREEN
    game_policy = GamePolicy.ALLOWED
    category = Category.FILES
    params_model = ReadTextParams
    observe = True
    timeout_s = 20.0

    async def run(self, params: ReadTextParams, ctx: ToolContext) -> ToolResult:
        if params.source == "selection":
            return await self._selection(ctx)
        return await self._document(params, ctx)

    # --- Selección ------------------------------------------------------------------------------

    async def _selection(self, ctx: ToolContext) -> ToolResult:
        from nyx.tools.app_action import game_processes
        from nyx.tools.type_text import _NOT_TARGETS, _TERMINALS
        from nyx.winapi import selection

        if ctx.game is not None and ctx.game.active:
            return ToolResult.fail("En partida no toco lo que tienes en pantalla")
        # La última ventana en la que estabas que no es Nyx (al escribirle, Nyx tiene el foco).
        listed = await asyncio.to_thread(windows.list_windows)
        target = next((w for w in listed if w.process not in _NOT_TARGETS), None)
        if target is None:
            return ToolResult.fail("No veo ninguna ventana con texto seleccionado")
        is_game = await asyncio.to_thread(
            games.window_is_game, target.hwnd, target.process, game_processes(ctx)
        )
        if is_game:
            return ToolResult.fail("Dentro de los juegos no toco nada")
        text = await asyncio.to_thread(selection.uia_selection, target.hwnd)
        if not text and target.process.lower() not in _TERMINALS:
            text = await asyncio.to_thread(selection.copy_selection, target.hwnd)
        if not text or not text.strip():
            return ToolResult.fail(
                f"No veo nada seleccionado en {target.title}",
                "selecciónalo, o cópialo y dime «resume lo copiado»",
            )
        clipped = text.strip()[:6000]
        return ToolResult(
            ok=True,
            message=f"He leído lo que tienes seleccionado en {target.title}.",
            display=" ".join(clipped.split())[:60],
            secondary="lo seleccionado",
            external=clipped,
            data={"source": "selection", "chars": len(clipped)},
        )

    # --- Documento ------------------------------------------------------------------------------

    async def _find(self, params: ReadTextParams, ctx: ToolContext) -> Path | ToolResult:
        from nyx.winapi import search

        allowed = KINDS[params.kind] if params.kind else SUFFIXES
        if params.folder:
            folder = await asyncio.to_thread(resolve_folder, ctx, params.folder)
            if isinstance(folder, ToolResult):
                return folder
            roots = [folder]
        else:
            roots = await asyncio.to_thread(search_roots)
        if params.file.strip():
            direct = Path(params.file)
            if direct.is_absolute() and await asyncio.to_thread(direct.is_file):
                return direct
            found, _ = await asyncio.to_thread(search.search, params.file, roots, 50)
        else:
            # Sin nombre: el último de ese tipo en la carpeta (o en Descargas, Documentos…).
            found = [p for root in roots for p in await asyncio.to_thread(_files_in, root)]
        found = [p for p in found if p.suffix.lower() in allowed]
        if not found:
            kind = _KIND_NAMES.get(params.kind or "", "documento")
            what = f"«{params.file}»" if params.file.strip() else f"ningún {kind}"
            return ToolResult.fail(f"No encuentro {what}", "dime parte de su nombre")
        newest = await asyncio.to_thread(by_date, found)
        return newest[0]

    async def _document(self, params: ReadTextParams, ctx: ToolContext) -> ToolResult:
        try:
            pages = parse_pages(params.pages)
        except DocumentError as e:
            return ToolResult.fail(str(e).capitalize())
        path = await self._find(params, ctx)
        if isinstance(path, ToolResult):
            return path
        try:
            doc = await asyncio.to_thread(extract, path, pages)
        except DocumentError as e:
            return ToolResult.fail(f"No puedo leer {path.name}: {e}")
        note = f" (he leído {doc.partial})" if doc.partial else ""
        return ToolResult(
            ok=True,
            message=f"He leído {path.name}{note}.",
            display=path.name,
            secondary=doc.partial or (f"{doc.pages} páginas" if doc.pages else "entero"),
            external=doc.text,
            data={"source": "document", "paths": [str(path)], "chars": len(doc.text)},
        )


def _files_in(root: Path) -> list[Path]:
    try:
        return [p for p in root.iterdir() if p.is_file() and p.suffix.lower() in SUFFIXES]
    except OSError:
        return []
