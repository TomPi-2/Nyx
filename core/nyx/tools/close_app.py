"""close_app: cierra una app como si se pulsara la X (amarilla; roja si hay cambios sin guardar).

Nunca se mata el proceso: la app recibe WM_CLOSE y puede preguntar si guardar. Deshacer
la vuelve a abrir.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

from pydantic import Field

from nyx.index.aliases import normalize
from nyx.index.model import Entry, Kind
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
from nyx.tools.focus_window import find_target_windows, process_for
from nyx.winapi import launch, windows
from nyx.winapi.windows import Window

# Títulos con cambios sin guardar: «*Sin título - Bloc de notas», «● SPEC.md - Visual Studio
# Code», «Documento1 - Word (sin guardar)»…
_UNSAVED = re.compile(
    r"^\s*[*●•]|\s[*●•]\s|\*\s*-\s|\(sin guardar\)|\bunsaved\b|\bmodificado\b", re.I
)
_OPEN_FOLDERS = frozenset(
    {
        "carpeta",
        "la carpeta",
        "esta carpeta",
        "carpeta abierta",
        "la carpeta abierta",
        "la carpeta que tengo abierta",
    }
)
_FOLDER_PREFIX = re.compile(
    r"^(?:la\s+)?carpeta(?:\s+(?:llamada|que\s+se\s+llama|de\s+nombre))?\s+"
)


class CloseAppParams(Params):
    name: str | None = Field(default=None, max_length=100, description="App (vacío = activa)")


def has_unsaved_changes(title: str) -> bool:
    return bool(_UNSAVED.search(title))


@dataclass(frozen=True, slots=True)
class Closing:
    label: str
    windows: list[Window]
    entry: Entry | None


class CloseApp(Tool[CloseAppParams]):
    name = "close_app"
    description = "Cierra una aplicación. Ej.: «cierra Spotify» (name=Spotify)."
    risk = Risk.YELLOW
    game_policy = GamePolicy.BLOCKED
    category = Category.APPS
    params_model = CloseAppParams

    async def prepare(self, params: CloseAppParams, ctx: ToolContext) -> Prepared:
        entry = None
        if params.name:
            norm = normalize(params.name)
            if norm in _OPEN_FOLDERS:
                every = await asyncio.to_thread(windows.list_windows)
                found = [w for w in every if w.process == "explorer.exe"][:1]
                if not found:
                    return Prepared("", error=ToolResult.fail("No veo ninguna carpeta abierta"))
                label = found[0].title
            elif _FOLDER_PREFIX.match(norm):
                folder_q = _FOLDER_PREFIX.sub("", norm).strip()
                fbest = ctx.index.confident(ctx.index.resolve(folder_q, {Kind.FOLDER}))
                query = fbest.entry.name if fbest else folder_q
                found = await asyncio.to_thread(windows.find_windows, query, None)
                found = [w for w in found if w.process == "explorer.exe"][:1]
                label = found[0].title if found else (fbest.entry.name if fbest else folder_q)
            else:
                best = ctx.index.confident(ctx.index.resolve(params.name, {Kind.APP, Kind.GAME}))
                entry = best.entry if best else None
                process = process_for(ctx, params.name)
                found = await asyncio.to_thread(find_target_windows, ctx, params.name)
                if process:
                    found = [w for w in found if w.process == process] or found[:1]
                else:
                    found = found[:1]
                label = entry.name if entry else params.name
        else:
            fg = await asyncio.to_thread(windows.foreground)
            found = [fg] if fg else []
            label = fg.title if fg else ""
        if not found:
            return Prepared(
                "", error=ToolResult.fail(f"No veo {label or 'ninguna ventana'} abierto")
            )
        unsaved = [w for w in found if has_unsaved_changes(w.title)]
        return Prepared(
            summary=f"Cerrar {label}",
            detail="tiene cambios sin guardar" if unsaved else "",
            count=len(found),
            risk=Risk.RED if unsaved else None,
            payload=Closing(label, found, entry),
        )

    async def execute(
        self, params: CloseAppParams, ctx: ToolContext, prepared: Prepared
    ) -> ToolResult:
        c: Closing = prepared.payload
        for w in c.windows:
            await asyncio.to_thread(windows.close_window, w.hwnd)
        undo = None
        if c.entry is not None:
            entry = c.entry

            async def reopen() -> str:
                await asyncio.to_thread(launch.launch, entry.launch)
                return f"Abriendo {entry.name} otra vez"

            undo = Undo(f"Cerrar {c.label}", reopen)
        return ToolResult(ok=True, message=f"Cerrando {c.label}", undo=undo)
