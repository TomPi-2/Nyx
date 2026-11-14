"""Nyx: núcleo del asistente de voz para Windows 11 (ver docs/SPEC.md)."""

import os

#: La versión es la de la app (tauri.conf.json, la misma con la que Velopack la empaqueta):
#: la app la pasa al lanzar el núcleo. Sin ella (desarrollo, pruebas), 0.0.0.
__version__ = os.environ.get("NYX_APP_VERSION") or "0.0.0"
