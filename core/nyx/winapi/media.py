"""Volumen (pycaw / Core Audio) y teclas multimedia.

Core Audio es COM: cada hilo que lo use necesita CoInitialize. Las funciones de aquí se
llaman desde asyncio.to_thread, así que inicializan COM ellas mismas.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator

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


def set_app(process: str, level: int | None = None, mute: bool | None = None) -> int:
    """Cambia el volumen de las sesiones de un proceso. Devuelve cuántas se cambiaron."""
    from pycaw.pycaw import AudioUtilities

    changed = 0
    with _com():
        for s in AudioUtilities.GetAllSessions():
            if not s.Process or s.Process.name().lower() != process:
                continue
            volume = s.SimpleAudioVolume
            if level is not None:
                volume.SetMasterVolume(max(0, min(100, level)) / 100, None)
            if mute is not None:
                volume.SetMute(1 if mute else 0, None)
            changed += 1
    return changed
