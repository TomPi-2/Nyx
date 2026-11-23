"""Dónde está cada cosa al medir desde el código (sin el instalador)."""

from __future__ import annotations

from pathlib import Path

from nyx.paths import local_dir
from nyx.services import whisper_server_path
from nyx.settings.model import Settings

# La compilación portable (todas las variantes de CPU y Vulkan; CLAUDE.md).
PORTABLE_WHISPER = Path(r"C:\dev\tools\whisper.cpp\build-portable\bin\Release\whisper-server.exe")


def whisper_server(given: Path | None, settings: Settings) -> Path | None:
    """whisper-server: el pedido, el de los ajustes, el del Nyx instalado o el portable."""
    installed = (
        local_dir().parent / "TepnyxNyx" / "current" / "core" / "bin" / "whisper"
    ) / "whisper-server.exe"
    for path in (given, whisper_server_path(settings), installed, PORTABLE_WHISPER):
        if path is not None and path.exists():
            return path
    return None
