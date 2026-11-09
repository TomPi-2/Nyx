"""Apps del menú Inicio (escritorio y Store) a través de shell:AppsFolder.

Es la misma lista que muestra Inicio → Todas las apps: incluye los accesos directos .lnk
y las apps empaquetadas, y cada una se abre con su AppID. Además se leen los .lnk del
menú Inicio para saber qué ejecutable lanza cada acceso (sirve para encontrar sus ventanas).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from nyx.index.aliases import generate
from nyx.index.model import Entry, Kind, Launch, LaunchKind

log = logging.getLogger(__name__)

# Entradas de Inicio que no son apps útiles por voz.
_SKIP_WORDS = ("uninstall", "desinstalar", "readme", "léame", "help", "ayuda de", "release notes")


def start_menu_dirs() -> list[Path]:
    dirs = []
    for var in ("APPDATA", "ProgramData"):
        if root := os.environ.get(var):
            dirs.append(Path(root) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    return dirs


def shortcut_targets() -> dict[str, str]:
    """Nombre del acceso directo → ejecutable (en minúsculas, solo el nombre del archivo)."""
    import win32com.client

    shell = win32com.client.Dispatch("WScript.Shell")
    targets: dict[str, str] = {}
    for root in start_menu_dirs():
        for lnk in root.rglob("*.lnk"):
            try:
                target = str(shell.CreateShortcut(str(lnk)).TargetPath)
            except Exception:
                continue
            if target.lower().endswith(".exe"):
                targets[lnk.stem.casefold()] = Path(target).name.lower()
    return targets


def scan() -> list[Entry]:
    import win32com.client

    shell = win32com.client.Dispatch("Shell.Application")
    folder = shell.NameSpace("shell:AppsFolder")
    targets = shortcut_targets()
    entries: list[Entry] = []
    for item in folder.Items():
        name, app_id = str(item.Name).strip(), str(item.Path).strip()
        if not name or not app_id or any(w in name.casefold() for w in _SKIP_WORDS):
            continue
        if app_id.lower().startswith(("http://", "https://")):
            continue  # enlaces web del menú Inicio (los cubre la tabla de webs)
        process = targets.get(name.casefold())
        if process is None and app_id.lower().endswith(".exe"):
            process = Path(app_id).name.lower()
        entries.append(
            Entry(
                key=f"app:{app_id.casefold()}",
                kind=Kind.APP,
                name=name,
                launch=Launch(LaunchKind.APPS_FOLDER, app_id),
                source="apps",
                process=process,
                aliases=generate(name),
            )
        )
    return entries
