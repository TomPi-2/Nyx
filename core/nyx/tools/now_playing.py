"""now_playing: qué suena ahora (título, artista y app) con la sesión multimedia de Windows.

Verde, `observe` (el modelo lo cuenta en una frase) y permitida en partida. Usa el control
multimedia de Windows (SMTC), como `winapi/media.py`: sirve para Spotify, el navegador
(YouTube, Twitch…) y cualquier app que se anuncie a Windows.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass

from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult

log = logging.getLogger(__name__)

# Trozo del identificador de la app (AUMID) → nombre para decirlo. El orden importa: «operagx»
# antes que «opera».
_APP_NAMES = (
    ("spotify", "Spotify"),
    ("operagx", "Opera GX"),
    ("opera", "Opera"),
    ("chrome", "Chrome"),
    ("msedge", "Edge"),
    ("firefox", "Firefox"),
    ("brave", "Brave"),
    ("vivaldi", "Vivaldi"),
    ("zunemusic", "Reproductor multimedia"),
    ("zunevideo", "Películas y TV"),
    ("vlc", "VLC"),
    ("itunes", "iTunes"),
    ("applemusic", "Apple Music"),
    ("deezer", "Deezer"),
    ("tidal", "TIDAL"),
)


@dataclass(frozen=True, slots=True)
class NowPlaying:
    title: str
    artist: str
    app: str
    playing: bool  # False: en pausa


def app_label(aumid: str) -> str:
    """«Spotify.exe» → «Spotify»; «OperaSoftware.OperaGXWebBrowser.1751…» → «Opera GX»."""
    key = aumid.casefold().replace(" ", "")
    for part, name in _APP_NAMES:
        if part in key:
            return name
    tail = aumid.split("!")[-1].rsplit("\\", 1)[-1]
    return tail.removesuffix(".exe").removesuffix(".EXE") or "otra app"


async def _read_smtc() -> NowPlaying | None:
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as Manager,
    )
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status,
    )

    manager = await Manager.request_async()
    sessions = list(manager.get_sessions())
    if not sessions:
        return None

    def is_playing(session: object) -> bool:
        info = session.get_playback_info()  # type: ignore[attr-defined]
        return info is not None and info.playback_status == Status.PLAYING

    # La que suena de verdad; si ninguna, la que Windows da por actual (en pausa).
    session = next((s for s in sessions if is_playing(s)), None)
    session = session or manager.get_current_session() or sessions[0]
    props = await session.try_get_media_properties_async()
    title = (props.title if props else "").strip()
    artist = (props.artist if props else "").strip()
    return NowPlaying(
        title, artist, app_label(session.source_app_user_model_id), is_playing(session)
    )


def read_now_playing() -> NowPlaying | None:
    """Lo que suena (o está en pausa) ahora, o None si ninguna app tiene sesión multimedia."""
    return asyncio.run(_read_smtc())


class NowPlayingParams(Params):
    pass


class NowPlayingTool(Tool[NowPlayingParams]):
    name = "now_playing"
    description = "Dice qué canción o vídeo suena ahora. Ej.: «¿qué suena?», «¿quién canta esto?»."
    risk = Risk.GREEN
    game_policy = GamePolicy.ALLOWED
    category = Category.AUDIO
    params_model = NowPlayingParams
    observe = True

    def __init__(self, reader: Callable[[], NowPlaying | None] = read_now_playing) -> None:
        self._reader = reader

    async def run(self, params: NowPlayingParams, ctx: ToolContext) -> ToolResult:
        try:
            now = await asyncio.to_thread(self._reader)
        except Exception:
            log.warning("No se pudo leer la sesión multimedia de Windows", exc_info=True)
            return ToolResult.fail("No he podido ver qué suena")
        if now is None or not now.title:
            return ToolResult(ok=True, message="No suena nada ahora", display="No suena nada")
        by = f" de {now.artist}" if now.artist else ""
        state = "Suena" if now.playing else "En pausa:"
        return ToolResult(
            ok=True,
            message=f"{state} «{now.title}»{by} en {now.app}",
            display=now.title,
            secondary=" · ".join(p for p in (now.artist, now.app) if p),
            data={"playing": now.playing},
        )
