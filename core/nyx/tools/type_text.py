"""type_text: escribe texto en la app activa con SendInput (amarilla, bloqueada en partida, 6.10).

Reutiliza `nyx/winapi/keys.py` (`keys.write`) y comprueba que la ventana de destino no sea ni Nyx
ni un juego (`winapi/games.py`), igual que `send_hotkey`. Máximo 2.000 caracteres. Ofrece deshacer
durante 30 s (envía Ctrl+Z a la misma ventana).

Sube a **roja** (confirmación con el texto a la vista) en dos casos, porque ahí escribir ya no es
solo escribir (SPEC sección 8):
- el texto lleva saltos de línea o tabuladores: Intro envía mensajes y ejecuta órdenes, y Tab
  cambia de campo;
- la ventana es una terminal: lo escrito es una orden, y `run_powershell` es siempre roja.
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
from nyx.tools.focus_window import find_target_windows
from nyx.winapi import games, keys, windows

FOCUS_SETTLE_S = 0.15
MAX_TEXT_LEN = 2000
_NOT_TARGETS = {"nyx-ui.exe", "nyx.exe"}
# Terminales y consolas (las integradas en un editor no se pueden distinguir por el proceso).
_TERMINALS = frozenset(
    {
        "windowsterminal.exe",
        "wt.exe",
        "cmd.exe",
        "powershell.exe",
        "pwsh.exe",
        "conhost.exe",
        "openconsole.exe",
        "bash.exe",
        "wsl.exe",
        "mintty.exe",
        "git-bash.exe",
        "alacritty.exe",
        "wezterm-gui.exe",
        "hyper.exe",
        "tabby.exe",
    }
)


def _preview(text: str, limit: int = 50) -> str:
    flat = " ".join(text.replace("\n", " ⏎ ").split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


class TypeTextParams(Params):
    text: str = Field(min_length=1, max_length=MAX_TEXT_LEN, description="Texto a escribir")
    app: str | None = Field(default=None, max_length=100, description="App (vacío = activa)")


class TypeText(Tool[TypeTextParams]):
    name = "type_text"
    description = (
        "Escribe texto en la app activa o en la app indicada. "
        "Ej.: «escribe en el Bloc de notas hola» (app=Bloc de notas, text=hola)."
    )
    risk = Risk.YELLOW
    game_policy = GamePolicy.BLOCKED
    category = Category.WINDOWS
    params_model = TypeTextParams

    async def prepare(self, params: TypeTextParams, ctx: ToolContext) -> Prepared:
        short = _preview(params.text)
        if params.app:
            found = await asyncio.to_thread(find_target_windows, ctx, params.app)
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

        text = params.text.replace("\r\n", "\n").replace("\r", "\n")
        presses = keys.presses_keys(text)
        terminal = target.process.lower() in _TERMINALS
        if presses or terminal:
            # Se confirma viendo el texto entero (o casi): es lo que se va a enviar o ejecutar.
            how = "y pulsar Intro" if "\n" in text else ""
            where = f"la terminal ({target.title})" if terminal else target.title
            return Prepared(
                summary=" ".join(f"Escribir en {where} {how}".split()),
                detail=_preview(text, 200),
                risk=Risk.RED,
                payload=(target.hwnd, text, target.title),
            )
        return Prepared(
            summary=f"Escribir en {target.title}",
            detail=short,
            payload=(target.hwnd, text, target.title),
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

        if not await asyncio.to_thread(keys.write, text):
            return ToolResult.fail(
                f"Windows no me deja escribir en {title}", "¿es una ventana de administrador?"
            )

        async def revert() -> str:
            # Ctrl+Z solo a la ventana donde se escribió: si no se puede volver a ella, no se
            # pulsa (iría a otra app, o a un juego).
            cur = await asyncio.to_thread(windows.foreground)
            if cur is None or cur.hwnd != hwnd:
                if not await asyncio.to_thread(windows.activate, hwnd):
                    raise OSError(f"no puedo volver a {title}")
                await asyncio.sleep(FOCUS_SETTLE_S)
            await asyncio.to_thread(keys.press, keys.parse("ctrl+z"))
            return f"Deshecho lo escrito en {title}"

        return ToolResult(
            ok=True,
            message=prepared.summary,
            undo=Undo(summary=prepared.summary, action=revert),
        )
