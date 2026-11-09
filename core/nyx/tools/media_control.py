"""media_control: reproducir/pausar, siguiente, anterior, parar (verde).

Usa las teclas multimedia de Windows: funciona con Spotify, YouTube en el navegador y
cualquier app que las respete.
"""

from __future__ import annotations

import asyncio
from typing import Literal

from pydantic import Field

from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult
from nyx.winapi import media


class MediaControlParams(Params):
    action: Literal["play_pause", "next", "previous", "stop"] = Field(
        description="play_pause sirve para pausar y para reanudar"
    )


class MediaControl(Tool[MediaControlParams]):
    name = "media_control"
    description = (
        "Controla la música o el vídeo que suena. Ej.: «pausa», «reanuda» y «pon música» "
        "(play_pause), "
        "«siguiente canción» (next), «la anterior» (previous)."
    )
    risk = Risk.GREEN
    game_policy = GamePolicy.ALLOWED
    category = Category.AUDIO
    params_model = MediaControlParams

    async def run(self, params: MediaControlParams, ctx: ToolContext) -> ToolResult:
        await asyncio.to_thread(media.press_media_key, params.action)
        return ToolResult(ok=True, message=f"Multimedia: {params.action}")
