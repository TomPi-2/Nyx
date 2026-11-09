r"""Rutas de datos de Nyx.

- %APPDATA%\Nyx: ajustes y datos del usuario (viajan con el perfil).
- %LOCALAPPDATA%\Nyx: modelos, registros y caché (solo de esta máquina).
"""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "Nyx"


def _base(env_var: str, fallback: str) -> Path:
    root = os.environ.get(env_var)
    return Path(root) / APP_NAME if root else Path.home() / fallback / APP_NAME


def roaming_dir() -> Path:
    return _base("APPDATA", ".config")


def local_dir() -> Path:
    return _base("LOCALAPPDATA", ".local/share")


def logs_dir() -> Path:
    return local_dir() / "logs"


def models_dir() -> Path:
    return local_dir() / "models"
