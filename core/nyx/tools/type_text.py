"""type_text: escribe texto en la app activa con SendInput (amarilla, bloqueada en partida, 6.10).

Reutiliza `nyx/winapi/keys.py` (`keys.write`) y comprueba que la ventana de destino no sea ni Nyx
ni un juego (`winapi/games.py`), igual que `send_hotkey`. Máximo 2.000 caracteres. Ofrece deshacer
durante 30 s (envía Ctrl+Z a la misma ventana).
"""

from __future__ import annotations

import asyncio

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
from nyx.tools.focus_window import process_for
from nyx.winapi import games, keys, windows

FOCUS_SETTLE_S = 0.15
MAX_TEXT_LEN = 2000
_NOT_TARGETS = {"nyx-ui.exe", "nyx.exe"}


def _preview(text: str, limit: int = 50) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


class TypeTextParams(Params):
    text: str = Field(min_length=1, max_length=MAX_TEXT_LEN, description="Texto a escribir")
    app: str | None = Field(default=None, max_length=100, description="App (vacío = activa)")


class TypeText(Tool[TypeTextParams]):
    name = "type_text"
    description = (
        "Escribe texto en la app activa. "
        "Ej.: «escribe llego en 10 minutos» (text=llego en 10 minutos)."
    )
    risk = Risk.YELLOW
    game_policy = GamePolicy.BLOCKED
    category = Category.WINDOWS
    params_model = TypeTextParams

    async def prepare(self, params: TypeTextParams, ctx: ToolContext) -> Prepared:
        short = _preview(params.text)
        if params.app:
            found = await asyncio.to_thread(
                windows.find_windows, params.app, process_for(ctx, params.app)
            )
            if not found:
                return Prepared(
                    summary=short,
                    error=ToolResult.fail(
                        f"No veo ninguna ventana de {params.app}", "¿está abierta?"
                    ),
                )
            target = found[0]
        else:
            fg = await asyncio.to_thread(windows.foreground)
            if fg is None or fg.process in _NOT_TARGETS or not fg.title:
                return Prepared(
                    summary=short,
                    error=ToolResult.fail("¿En qué app?", "no hay ninguna ventana activa"),
                )
            target = fg

        if target.process in _NOT_TARGETS:
            return Prepared(summary=short, error=ToolResult.fail("Eso no lo escribo en Nyx"))

        from nyx.tools.app_action import game_processes

        is_game = await asyncio.to_thread(
            games.window_is_game, target.hwnd, target.process, game_processes(ctx)
        )
        if is_game:
            return Prepared(
                summary=short, error=ToolResult.fail("Dentro de los juegos no toco nada")
            )

        return Prepared(
            summary=f"Escribir en {target.title}",
            detail=short,
            payload=(target.hwnd, params.text, target.title),
        )

    async def execute(
        self, params: TypeTextParams, ctx: ToolContext, prepared: Prepared
    ) -> ToolResult:
        hwnd, text, title = prepared.payload
        fg = await asyncio.to_thread(windows.foreground)
        if fg is None or fg.hwnd != hwnd:
            if not await asyncio.to_thread(windows.activate, hwnd):
                return ToolResult.fail(f"Windows no me deja traer {title} al frente")
            await asyncio.sleep(FOCUS_SETTLE_S)

        await asyncio.to_thread(keys.write, text)

        async def revert() -> str:
            cur = await asyncio.to_thread(windows.foreground)
            if cur is None or cur.hwnd != hwnd:
                await asyncio.to_thread(windows.activate, hwnd)
                await asyncio.sleep(FOCUS_SETTLE_S)
            await asyncio.to_thread(keys.press, keys.parse("ctrl+z"))
            return f"Deshecho lo escrito en {title}"

        return ToolResult(
            ok=True,
            message=prepared.summary,
            undo=Undo(summary=prepared.summary, action=revert),
        )
