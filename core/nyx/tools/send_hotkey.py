"""send_hotkey: pulsa un atajo de teclado en una app (amarillo; bloqueado en partida).

SPEC secciones 7 y 8: «abre una pestaña nueva en el bloc de notas» = Ctrl+T en su ventana.
Lista de bloqueo fija (Alt+F4, Mayús+Supr, Win+R…, ver winapi/keys.py). Si se nombra una app,
primero se trae su ventana al frente; si no, va a la ventana activa (nunca a la de Nyx ni al
escritorio).
"""

from __future__ import annotations

import asyncio

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
from nyx.tools.focus_window import process_for
from nyx.winapi import games, keys, windows

FOCUS_SETTLE_S = 0.15  # tras traer la ventana al frente, antes de pulsar
_NOT_TARGETS = {"nyx-ui.exe", "nyx.exe"}


class SendHotkeyParams(Params):
    keys: str = Field(min_length=1, max_length=40, description="Atajo (p. ej. ctrl+s)")
    app: str | None = Field(default=None, max_length=100, description="App (vacío = activa)")


class SendHotkey(Tool[SendHotkeyParams]):
    name = "send_hotkey"
    description = "Pulsa un atajo de teclado en una app. Ej.: «pulsa control s» (keys=ctrl+s)."
    risk = Risk.YELLOW
    game_policy = GamePolicy.BLOCKED
    category = Category.WINDOWS
    params_model = SendHotkeyParams

    async def prepare(self, params: SendHotkeyParams, ctx: ToolContext) -> Prepared:
        try:
            hotkey = keys.parse(params.keys)
        except ValueError as e:
            return Prepared(
                summary=params.keys, error=ToolResult.fail(f"No entiendo el atajo: {e}")
            )
        if reason := keys.blocked_reason(hotkey):
            return Prepared(
                summary=hotkey.label,
                error=ToolResult.fail(f"No pulso {hotkey.label}", reason),
            )
        if params.app:
            found = await asyncio.to_thread(
                windows.find_windows, params.app, process_for(ctx, params.app)
            )
            if not found:
                return Prepared(
                    summary=hotkey.label,
                    error=ToolResult.fail(
                        f"No veo ninguna ventana de {params.app}", "¿está abierta?"
                    ),
                )
            target = found[0]
        else:
            fg = await asyncio.to_thread(windows.foreground)
            if fg is None or fg.process in _NOT_TARGETS or not fg.title:
                return Prepared(
                    summary=hotkey.label,
                    error=ToolResult.fail("¿En qué app?", "no hay ninguna ventana activa"),
                )
            target = fg
        if target.process in _NOT_TARGETS:
            return Prepared(summary=hotkey.label, error=ToolResult.fail("Eso no lo pulso en Nyx"))
        from nyx.tools.app_action import game_processes

        is_game = await asyncio.to_thread(
            games.window_is_game, target.hwnd, target.process, game_processes(ctx)
        )
        if is_game:
            return Prepared(
                summary=hotkey.label, error=ToolResult.fail("Dentro de los juegos no toco nada")
            )
        return Prepared(
            summary=f"Pulsar {hotkey.label} en {target.title}",
            payload=(target.hwnd, hotkey, target.title),
        )

    async def execute(
        self, params: SendHotkeyParams, ctx: ToolContext, prepared: Prepared
    ) -> ToolResult:
        hwnd, hotkey, title = prepared.payload
        fg = await asyncio.to_thread(windows.foreground)
        if fg is None or fg.hwnd != hwnd:
            if not await asyncio.to_thread(windows.activate, hwnd):
                return ToolResult.fail(f"Windows no me deja traer {title} al frente")
            await asyncio.sleep(FOCUS_SETTLE_S)
        await asyncio.to_thread(keys.press, hotkey)
        return ToolResult(ok=True, message=prepared.summary)
