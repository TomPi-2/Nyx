r"""Los documentos que has abierto hace poco (tarea 8.06). Solo lectura.

Windows deja un acceso directo por cada archivo abierto en `%APPDATA%\Microsoft\Windows\Recent`;
la fecha del acceso directo es la de la última vez que se abrió. Aquí se resuelven (con
`WScript.Shell`, como los del menú Inicio) y se quedan los que siguen existiendo. Sin indexar
nada nuevo.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

log = logging.getLogger(__name__)

Kind = Literal["any", "word", "excel", "powerpoint", "pdf", "image", "video", "text"]

EXTENSIONS: dict[str, frozenset[str]] = {
    "word": frozenset({".doc", ".docx", ".docm", ".odt", ".rtf"}),
    "excel": frozenset({".xls", ".xlsx", ".xlsm", ".ods", ".csv"}),
    "powerpoint": frozenset({".ppt", ".pptx", ".odp"}),
    "pdf": frozenset({".pdf"}),
    "image": frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".tif"}),
    "video": frozenset({".mp4", ".mkv", ".mov", ".avi", ".webm"}),
    "text": frozenset({".txt", ".md", ".log", ".json", ".ini"}),
}
MAX_LINKS = 400  # los más recientes; la carpeta puede tener miles


@dataclass(frozen=True, slots=True)
class Recent:
    path: Path
    opened: datetime


def recent_dir() -> Path:
    return Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Recent"


def _targets(links: list[Path]) -> list[tuple[Path, str]]:
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()  # en un hilo aparte
    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        out = []
        for lnk in links:
            try:
                out.append((lnk, str(shell.CreateShortcut(str(lnk)).TargetPath)))
            except Exception:
                continue
        return out
    finally:
        pythoncom.CoUninitialize()


def recent_files(
    kind: Kind = "any", limit: int = 10, *, folder: Path | None = None
) -> list[Recent]:
    """Los archivos abiertos hace poco, el último primero; solo los que aún existen."""
    root = folder or recent_dir()
    try:
        links = sorted(root.glob("*.lnk"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return []
    wanted = EXTENSIONS.get(kind)
    out: list[Recent] = []
    seen: set[str] = set()
    for lnk, target in _targets(links[:MAX_LINKS]):
        path = Path(target)
        key = target.lower()
        if not target or key in seen:
            continue
        if wanted is not None and path.suffix.lower() not in wanted:
            continue
        if wanted is None and path.suffix.lower() in ("", ".exe", ".lnk"):
            continue  # carpetas y programas no son documentos
        try:
            if not path.is_file():
                continue
            opened = datetime.fromtimestamp(lnk.stat().st_mtime)
        except OSError:
            continue
        seen.add(key)
        out.append(Recent(path, opened))
        if len(out) >= limit:
            break
    return out
