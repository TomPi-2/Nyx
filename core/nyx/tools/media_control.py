"""media_control: reproducir, pausar, siguiente, anterior, parar (verde).

Primero el control multimedia de Windows (SMTC): elige la sesión («de YouTube» → el
navegador, «de Spotify» → Spotify) y distingue pausar de reanudar. Si no hay sesión o falla,
las teclas multimedia (algunos navegadores, como Opera GX, las ignoran).
"""

from __future__ import annotations

import asyncio
import time
from typing import Literal

from pydantic import Field

from nyx.index.model import Kind
from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult
from nyx.winapi import media

SPOTIFY_WAIT_S = 12.0  # lo que puede tardar Spotify en abrir y registrar su sesión


class MediaControlParams(Params):
    action: Literal["pause", "play", "play_pause", "next", "previous", "stop"] = Field(
        description="pause: pausar · play: reanudar · play_pause: alternar"
    )
    source: str | None = Field(
        default=None, max_length=60, description="De dónde: youtube, spotify, twitch…"
    )
    music: bool = Field(
        default=False,
        description="true si piden música sin decir dónde («pon música»): va a Spotify",
    )


class MediaControl(Tool[MediaControlParams]):
    name = "media_control"
    description = (
        "Controla la música o el vídeo que suena. Ej.: «pausa» (pause), «pausa el vídeo de "
        "YouTube» (pause, source=youtube), «reanuda» (play), «pon música» (play, music=true), "
        "«siguiente "
        "canción» (next), «la anterior» (previous)."
    )
    risk = Risk.GREEN
    game_policy = GamePolicy.ALLOWED
    category = Category.AUDIO
    params_model = MediaControlParams

    async def run(self, params: MediaControlParams, ctx: ToolContext) -> ToolResult:
        if params.music and not params.source and params.action == "play":
            music = await self._music(ctx)
            if music is not None:
                return music
        app = await asyncio.to_thread(media.smtc_control, params.action, params.source)
        if app is not None:
            return ToolResult(ok=True, message=f"Multimedia: {params.action} ({app})")
        key = params.action if params.action in media.VK_MEDIA else "play_pause"
        await asyncio.to_thread(media.press_media_key, key)
        return ToolResult(ok=True, message=f"Multimedia: {params.action} (tecla)")

    async def _music(self, ctx: ToolContext) -> ToolResult | None:
        """«Pon música» sin decir dónde: en Spotify si está instalada (más adelante, en la app
        donde el usuario suela escucharla). None: no hay Spotify, se hace lo de siempre."""
        entry = ctx.index.confident(ctx.index.resolve("spotify", {Kind.APP}))
        if entry is None:
            return None
        if await asyncio.to_thread(media.smtc_control, "play", "spotify", True):
            return ToolResult(ok=True, message="Música en Spotify")
        # Cerrada: se abre en segundo plano y se le da al play cuando Windows ve su sesión.
        from nyx.tools.open_app import OpenApp, OpenAppParams

        opened = await OpenApp().run(OpenAppParams(name=entry.entry.name, focus=False), ctx)
        if not opened.ok:
            return None
        deadline = time.monotonic() + SPOTIFY_WAIT_S
        while time.monotonic() < deadline:
            await asyncio.sleep(0.5)
            if await asyncio.to_thread(media.smtc_control, "play", "spotify", True):
                return ToolResult(ok=True, message="Música en Spotify")
        return ToolResult(
            ok=True,
            message="Abriendo Spotify",
            display="Spotify",
            secondary="dale al play cuando abra",
        )
