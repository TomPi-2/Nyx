"""Carpetas del usuario (Known Folders, con la redirección a OneDrive) y su primer nivel."""

from __future__ import annotations

import logging
from pathlib import Path

from nyx.index.aliases import generate
from nyx.index.model import Entry, Kind, Launch, LaunchKind

log = logging.getLogger(__name__)

# FOLDERID → nombre en español y alias
KNOWN_FOLDERS: dict[str, tuple[str, tuple[str, ...]]] = {
    "FOLDERID_Documents": ("Documentos", ("documents", "mis documentos")),
    "FOLDERID_Downloads": ("Descargas", ("downloads", "mis descargas")),
    "FOLDERID_Desktop": ("Escritorio", ("desktop",)),
    "FOLDERID_Pictures": ("Imágenes", ("fotos", "pictures", "mis imagenes")),
    "FOLDERID_Music": ("Música", ("music", "mi musica")),
    "FOLDERID_Videos": ("Vídeos", ("videos", "mis videos")),
    "FOLDERID_Profile": ("Carpeta personal", ("mi carpeta", "usuario", "carpeta de usuario")),
}

MAX_CHILDREN = 200


def known_folders() -> dict[str, Path]:
    from win32comext.shell import shell, shellcon

    found: dict[str, Path] = {}
    for folder_id, (name, _) in KNOWN_FOLDERS.items():
        try:
            path = Path(shell.SHGetKnownFolderPath(getattr(shellcon, folder_id), 0, None))
        except Exception:
            continue
        if path.exists():
            found[name] = path
    return found


def folder_entry(name: str, path: Path, extra: tuple[str, ...] = ()) -> Entry:
    return Entry(
        key=f"folder:{str(path).casefold()}",
        kind=Kind.FOLDER,
        name=name,
        launch=Launch(LaunchKind.PATH, str(path)),
        source="folders",
        aliases=generate(name, extra),
    )


def scan(roots: dict[str, Path] | None = None) -> list[Entry]:
    roots = roots if roots is not None else known_folders()
    extras = {name: aliases for name, aliases in KNOWN_FOLDERS.values()}
    entries = [folder_entry(name, path, extras.get(name, ())) for name, path in roots.items()]
    for name, path in roots.items():
        if name == "Carpeta personal":
            continue
        try:
            children = sorted(
                p for p in path.iterdir() if p.is_dir() and not p.name.startswith(".")
            )
        except OSError:
            continue
        for child in children[:MAX_CHILDREN]:
            # «Fondos» y también «Fondos de Imágenes», por si hay dos con el mismo nombre.
            entries.append(folder_entry(child.name, child, (f"{child.name} de {name}",)))
    return entries
