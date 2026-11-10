"""media_control: reproducir, pausar, siguiente, anterior, parar (verde).

Primero el control multimedia de Windows (SMTC): elige la sesión («de YouTube» → el
navegador, «de Spotify» → Spotify) y distingue pausar de reanudar. Si no hay sesión o falla,
las teclas multimedia (algunos navegadores, como Opera GX, las ignoran).
"""

from __future__ import annotations

import asyncio
from typing import Literal

from pydantic import Field

from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult
from nyx.winapi import media


class MediaControlParams(Params):
    action: Literal["pause", "play", "play_pause", "next", "previous", "stop"] = Field(
        description="pause: pausar · play: reanudar · play_pause: alternar"
    )
    source: str | None = Field(
        default=None, max_length=60, description="De dónde: youtube, spotify, twitch…"
    )


class MediaControl(Tool[MediaControlParams]):
    name = "media_control"
    description = (
        "Controla la música o el vídeo que suena. Ej.: «pausa» (pause), «pausa el vídeo de "
        "YouTube» (pause, source=youtube), «reanuda» y «pon música» (play), «siguiente "
        "canción» (next), «la anterior» (previous)."
    )
    risk = Risk.GREEN
    game_policy = GamePolicy.ALLOWED
    category = Category.AUDIO
    params_model = MediaControlParams

    async def run(self, params: MediaControlParams, ctx: ToolContext) -> ToolResult:
        app = await asyncio.to_thread(media.smtc_control, params.action, params.source)
        if app is not None:
            return ToolResult(ok=True, message=f"Multimedia: {params.action} ({app})")
        key = params.action if params.action in media.VK_MEDIA else "play_pause"
        await asyncio.to_thread(media.press_media_key, key)
        return ToolResult(ok=True, message=f"Multimedia: {params.action} (tecla)")
