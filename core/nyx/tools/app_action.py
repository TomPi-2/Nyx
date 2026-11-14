"""app_action: una acción dentro de una app («pestaña nueva en el bloc de notas», «sube el
volumen de Spotify», «silencia el micro en Discord») (amarilla; bloqueada en partida).

Busca la ventana de la app (o usa la activa), pulsa el atajo del catálogo (app_catalog.py) en
el idioma de Windows y, si la acción es «de fondo», devuelve el foco a donde estaba. Nunca
actúa dentro de un juego ni en Nyx.
"""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import Field, field_validator

from nyx.index.model import Kind
from nyx.tools.app_catalog import ALL_ACTIONS, all_actions, profile_for, windows_language
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
from nyx.tools.focus_window import process_for
from nyx.winapi import games, keys, windows

FOCUS_SETTLE_S = 0.15
REPEAT_GAP_S = 0.06
_NOT_TARGETS = {"nyx-ui.exe", "nyx.exe"}


class AppActionParams(Params):
    action: str = Field(description="Acción: " + ", ".join(ALL_ACTIONS))
    app: str | None = Field(default=None, max_length=100, description="App (vacío = activa)")
    times: int = Field(default=1, ge=1, le=10, description="Cuántas veces")

    @field_validator("action")
    @classmethod
    def known(cls, value: str) -> str:
        known = all_actions()  # también las de las extensiones instaladas
        if value not in known:
            raise ValueError(f"acción desconocida; usa una de: {', '.join(known)}")
        return value


def game_processes(ctx: ToolContext) -> set[str]:
    return {e.process for e in ctx.index.entries({Kind.GAME}) if e.process}


class AppAction(Tool[AppActionParams]):
    name = "app_action"
    description = (
        "Acción dentro de una app abierta. Ej.: «amplía la página» (action=zoom_in), "
        "«busca un canal en Discord» (app=Discord, action=quick_switcher)."
    )
    risk = Risk.YELLOW
    game_policy = GamePolicy.BLOCKED
    category = Category.WINDOWS

    def schema(self) -> dict[str, Any]:
        # La lista de acciones, al día: también las de las extensiones instaladas (7.04).
        out = super().schema()
        props = out["function"]["parameters"]["properties"]
        props["action"]["description"] = "Acción: " + ", ".join(all_actions())
        return out
    params_model = AppActionParams

    async def prepare(self, params: AppActionParams, ctx: ToolContext) -> Prepared:
        def fail(message: str, hint: str | None = None) -> Prepared:
            return Prepared(summary=params.action, error=ToolResult.fail(message, hint))

        if params.app:
            process = process_for(ctx, params.app)
            found = await asyncio.to_thread(windows.find_windows, params.app, process)
            named = profile_for(None, params.app)
            if not found and named is not None:  # «el navegador»: cualquiera de sus programas
                every = await asyncio.to_thread(windows.list_windows)
                found = [w for w in every if w.process in named.processes]
            if not found:
                return fail(f"No veo ninguna ventana de {params.app}", "¿está abierta?")
            target = found[0]
        else:
            fg = await asyncio.to_thread(windows.foreground)
            if fg is None or fg.process in _NOT_TARGETS:
                return fail("¿En qué app?", "no hay ninguna ventana activa")
            target = fg
        if target.process in _NOT_TARGETS:
            return fail("Eso no lo hago en Nyx")
        is_game = await asyncio.to_thread(
            games.window_is_game, target.hwnd, target.process, game_processes(ctx)
        )
        if is_game:
            return fail("Dentro de los juegos no toco nada")
        profile = profile_for(target.process, params.app)
        if profile is None:
            return fail(f"Aún no sé hacer cosas dentro de {params.app or target.title}")
        action = profile.actions.get(params.action)
        if action is None:
            options = ", ".join(a.label.lower() for a in profile.actions.values())
            return fail(f"En {profile.name} no sé hacer eso", f"sé: {options}")
        hotkey = keys.parse(action.keys_for(windows_language()))
        times = f" ×{params.times}" if params.times > 1 else ""
        return Prepared(
            summary=f"{action.label}{times} en {profile.name}",
            payload=(target.hwnd, hotkey, action.background, target.title),
        )

    async def execute(
        self, params: AppActionParams, ctx: ToolContext, prepared: Prepared
    ) -> ToolResult:
        hwnd, hotkey, background, title = prepared.payload
        previous = await asyncio.to_thread(windows.foreground)
        if previous is None or previous.hwnd != hwnd:
            if not await asyncio.to_thread(windows.activate, hwnd):
                return ToolResult.fail(f"Windows no me deja traer {title} al frente")
            await asyncio.sleep(FOCUS_SETTLE_S)
        for i in range(params.times):
            if i:
                await asyncio.sleep(REPEAT_GAP_S)
            await asyncio.to_thread(keys.press, hotkey)
        if background and previous is not None and previous.hwnd != hwnd:
            await asyncio.sleep(FOCUS_SETTLE_S)
            await asyncio.to_thread(windows.activate, previous.hwnd)
        return ToolResult(ok=True, message=prepared.summary, display=prepared.summary)
