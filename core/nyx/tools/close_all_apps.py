"""close_all_apps: cierra todas las apps abiertas, como si se pulsara la X en cada una (roja).

«Cierra todo», «cierra todas las aplicaciones» (paso 2 de Cerebro 2, 2026-11-24, opción
aprobada por el usuario). Siempre se confirma enumerando lo que se va a cerrar: «Voy a
cerrar Opera, Spotify y Discord. ¿Sigo?».

- Nunca se mata un proceso: cada ventana recibe WM_CLOSE y la app puede preguntar si guardar.
- No se tocan Nyx, el Explorador (escritorio, barra de tareas y carpetas) ni los juegos.
- Deshacer vuelve a abrir las apps que el índice conoce.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

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
from nyx.tools.close_app import has_unsaved_changes
from nyx.winapi import launch, windows
from nyx.winapi.windows import Window

#: Lo que «todo» no incluye: Nyx y el propio Windows.
KEEP_PROCESSES = frozenset(
    {
        "explorer.exe",
        "nyx-ui.exe",
        "nyx.exe",
        "shellexperiencehost.exe",
        "systemsettings.exe",
        "lockapp.exe",
    }
)
MAX_NAMED = 6  # en la pregunta, como mucho tantos nombres; el resto, «y N más»


class CloseAllAppsParams(Params):
    pass


@dataclass(frozen=True, slots=True)
class AppWindows:
    label: str
    windows: list[Window]
    entry: Entry | None


def group_windows(every: list[Window], ctx: ToolContext) -> list[AppWindows]:
    """Las ventanas que se cerrarían, agrupadas por app (en el orden en que se ven)."""
    games = {e.process for e in ctx.index.entries({Kind.GAME}) if e.process}
    by_process = {e.process: e for e in ctx.index.entries({Kind.APP}) if e.process}
    groups: dict[str, AppWindows] = {}
    for w in every:
        if w.process in KEEP_PROCESSES or w.process in games:
            continue
        group = groups.get(w.process)
        if group is None:
            entry = by_process.get(w.process)
            group = AppWindows(entry.name if entry else w.title, [], entry)
            groups[w.process] = group
        group.windows.append(w)
    return list(groups.values())


def spoken_list(labels: list[str]) -> str:
    """«Opera, Spotify y Discord»; con muchas, «…, Word y 3 más»."""
    named = labels[:MAX_NAMED]
    rest = len(labels) - len(named)
    if rest:
        return f"{', '.join(named)} y {rest} más"
    if len(named) == 1:
        return named[0]
    return f"{', '.join(named[:-1])} y {named[-1]}"


class CloseAllApps(Tool[CloseAllAppsParams]):
    name = "close_all_apps"
    description = (
        "Cierra todas las apps abiertas (pide confirmación). Ej.: «cierra todo», «cierra todas "
        "las aplicaciones». Para una sola, close_app."
    )
    risk = Risk.RED
    game_policy = GamePolicy.BLOCKED
    category = Category.APPS
    params_model = CloseAllAppsParams

    async def prepare(self, params: CloseAllAppsParams, ctx: ToolContext) -> Prepared:
        every = await asyncio.to_thread(windows.list_windows)
        groups = group_windows(every, ctx)
        if not groups:
            return Prepared("", error=ToolResult.fail("No hay ninguna app abierta que cerrar"))
        unsaved = [g.label for g in groups if any(has_unsaved_changes(w.title) for w in g.windows)]
        detail = f"Con cambios sin guardar: {spoken_list(unsaved)}" if unsaved else ""
        return Prepared(
            summary=f"Cerrar {spoken_list([g.label for g in groups])}",
            detail=detail,
            count=len(groups),
            payload=groups,
        )

    async def execute(
        self, params: CloseAllAppsParams, ctx: ToolContext, prepared: Prepared
    ) -> ToolResult:
        groups: list[AppWindows] = prepared.payload
        for group in groups:
            for w in group.windows:
                await asyncio.to_thread(windows.close_window, w.hwnd)
        known = [g.entry for g in groups if g.entry is not None]

        async def reopen() -> str:
            for entry in known:
                await asyncio.to_thread(launch.launch, entry.launch)
            return f"Abriendo otra vez {spoken_list([e.name for e in known])}"

        undo = Undo(f"Cerrar {len(groups)} apps", reopen) if known else None
        n = len(groups)
        return ToolResult(ok=True, message=f"Cerrando {n} app{'s' if n != 1 else ''}", undo=undo)
