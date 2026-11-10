"""Volumen (pycaw / Core Audio) y teclas multimedia.

Core Audio es COM: cada hilo que lo use necesita CoInitialize. Las funciones de aquí se
llaman desde asyncio.to_thread, así que inicializan COM ellas mismas.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Iterator
from typing import Any

log = logging.getLogger(__name__)

VK_MEDIA = {"next": 0xB0, "previous": 0xB1, "stop": 0xB2, "play_pause": 0xB3}


@contextlib.contextmanager
def _com() -> Iterator[None]:
    import comtypes

    comtypes.CoInitialize()
    try:
        yield
    finally:
        comtypes.CoUninitialize()


def press_media_key(action: str) -> None:
    import win32api
    import win32con

    vk = VK_MEDIA[action]
    win32api.keybd_event(vk, 0, win32con.KEYEVENTF_EXTENDEDKEY, 0)
    win32api.keybd_event(vk, 0, win32con.KEYEVENTF_EXTENDEDKEY | win32con.KEYEVENTF_KEYUP, 0)


def get_master() -> tuple[int, bool]:
    """(volumen 0–100, silenciado) del dispositivo de salida predeterminado."""
    from pycaw.pycaw import AudioUtilities

    with _com():
        endpoint = AudioUtilities.GetSpeakers().EndpointVolume
        return round(endpoint.GetMasterVolumeLevelScalar() * 100), bool(endpoint.GetMute())


def set_master(level: int | None = None, mute: bool | None = None) -> tuple[int, bool]:
    from pycaw.pycaw import AudioUtilities

    with _com():
        endpoint = AudioUtilities.GetSpeakers().EndpointVolume
        if level is not None:
            endpoint.SetMasterVolumeLevelScalar(max(0, min(100, level)) / 100, None)
            if level > 0 and mute is None:
                endpoint.SetMute(0, None)  # subir el volumen quita el silencio, como en Windows
        if mute is not None:
            endpoint.SetMute(1 if mute else 0, None)
        return round(endpoint.GetMasterVolumeLevelScalar() * 100), bool(endpoint.GetMute())


def app_sessions() -> list[str]:
    """Procesos con sesión de audio (para el volumen por app)."""
    from pycaw.pycaw import AudioUtilities

    with _com():
        return sorted(
            {s.Process.name().lower() for s in AudioUtilities.GetAllSessions() if s.Process}
        )


def set_app(
    process: str,
    level: int | None = None,
    mute: bool | None = None,
    change: int | None = None,
) -> int | None:
    """Cambia el volumen de las sesiones de un proceso (exacto o relativo, «sube Spotify»).

    Devuelve el volumen resultante (0–100) o None si el proceso no tiene sesión de audio.
    """
    from pycaw.pycaw import AudioUtilities

    result: int | None = None
    with _com():
        for s in AudioUtilities.GetAllSessions():
            if not s.Process or s.Process.name().lower() != process:
                continue
            volume = s.SimpleAudioVolume
            target = level
            if change is not None:
                target = round(volume.GetMasterVolume() * 100) + change
            if target is not None:
                volume.SetMasterVolume(max(0, min(100, target)) / 100, None)
            if mute is not None:
                volume.SetMute(1 if mute else 0, None)
            result = round(volume.GetMasterVolume() * 100)
    return result


# --- Control multimedia de Windows (SMTC) ---
# Más fiable que las teclas multimedia (Opera GX, por ejemplo, las ignora) y permite elegir
# la sesión: «pausa el vídeo de YouTube» → la del navegador, «… de Spotify» → Spotify.

BROWSERS = ("opera", "chrome", "msedge", "edge", "firefox", "brave", "vivaldi", "browser")
WEB_SOURCES = {"youtube", "twitch", "netflix", "video", "navegador", "web", "prime", "disney"}


def _pick_session(sessions: list[Any], current: Any, source: str | None) -> Any:
    """La sesión que encaja con `source` («youtube», «spotify»…) o, si no, la actual."""
    if source:
        want = source.casefold().strip()
        ids = [(s, str(s.source_app_user_model_id).casefold()) for s in sessions]
        if want in WEB_SOURCES:
            for s, aumid in ids:
                if any(b in aumid for b in BROWSERS):
                    return s
        for s, aumid in ids:
            if want.replace(" ", "") in aumid.replace(" ", ""):
                return s
    return current or (sessions[0] if sessions else None)


async def _smtc(action: str, source: str | None) -> str | None:
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as Manager,
    )

    manager = await Manager.request_async()
    sessions = list(manager.get_sessions())
    session = _pick_session(sessions, manager.get_current_session(), source)
    if session is None:
        return None
    command = {
        "play": session.try_play_async,
        "pause": session.try_pause_async,
        "play_pause": session.try_toggle_play_pause_async,
        "next": session.try_skip_next_async,
        "previous": session.try_skip_previous_async,
        "stop": session.try_stop_async,
    }[action]
    if not await command():
        return None
    return str(session.source_app_user_model_id)


def smtc_control(action: str, source: str | None = None) -> str | None:
    """Pausa, reanuda, salta… la sesión multimedia elegida. Devuelve su app o None (sin
    sesiones o Windows no lo permite: entonces se usan las teclas multimedia)."""
    import asyncio

    try:
        return asyncio.run(_smtc(action, source))
    except Exception:
        log.debug("Control multimedia de Windows no disponible", exc_info=True)
        return None
