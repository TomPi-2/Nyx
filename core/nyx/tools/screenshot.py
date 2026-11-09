r"""screenshot: captura de un monitor, de todos o de la ventana activa (verde).

Se guarda en Imágenes\Capturas\Nyx y se copia al portapapeles.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult
from nyx.winapi import capture, windows

Target = Literal["current", "primary", "all", "window"]


class ScreenshotParams(Params):
    target: Target = Field(
        default="current",
        description="current = monitor de la ventana activa; primary; all = todos; window",
    )


def pictures_dir() -> Path:
    try:
        from win32comext.shell import shell, shellcon

        return Path(shell.SHGetKnownFolderPath(shellcon.FOLDERID_Pictures, 0, None))
    except Exception:
        return Path.home() / "Pictures"


def region_for(target: Target) -> windows.Rect:
    screens = windows.monitors()
    if target == "all":
        return (
            min(m.rect[0] for m in screens),
            min(m.rect[1] for m in screens),
            max(m.rect[2] for m in screens),
            max(m.rect[3] for m in screens),
        )
    if target == "primary":
        return next((m.rect for m in screens if m.primary), screens[0].rect)
    fg = windows.foreground()
    if fg is None:
        return next((m.rect for m in screens if m.primary), screens[0].rect)
    rect = windows.window_rect(fg.hwnd)
    if target == "window":
        return rect
    return screens[windows.monitor_of(rect, screens)].rect


def take(target: Target, folder: Path) -> Path:
    shot = capture.grab(region_for(target))
    path = folder / f"Nyx {datetime.now():%Y-%m-%d %H.%M.%S}.png"
    capture.save_png(shot, path)
    capture.copy_to_clipboard(shot)
    return path


class Screenshot(Tool[ScreenshotParams]):
    name = "screenshot"
    description = (
        "Hace una captura de pantalla, la guarda en Imágenes y la copia al portapapeles. Ej.: "
        "«haz una captura», «captura del monitor principal», «captura de esta ventana»."
    )
    risk = Risk.GREEN
    game_policy = GamePolicy.ALLOWED
    category = Category.CAPTURE
    params_model = ScreenshotParams

    async def run(self, params: ScreenshotParams, ctx: ToolContext) -> ToolResult:
        folder = pictures_dir() / "Capturas" / "Nyx"
        path = await asyncio.to_thread(take, params.target, folder)
        return ToolResult(
            ok=True,
            message="Captura guardada",
            display="Captura guardada",
            secondary="copiada al portapapeles",
            data={"path": str(path)},
        )
