"""Copia de seguridad de los datos de Nyx antes de actualizar, y restaurarla (SPEC §15).

Se copian los ajustes, el estado de las extensiones, la cola de la partida y las bases de
datos (alarmas y atajos aprendidos; con la copia de SQLite, que es coherente aunque estén
abiertas). Nada de modelos, registros ni grabaciones: pesan mucho y se pueden volver a crear.

Las copias van a `%LOCALAPPDATA%\\Nyx\\copias\\<fecha>-<versión>\\`; se guardan las tres
últimas y las viejas van a la papelera (nunca borrado permanente).
"""

from __future__ import annotations

import json
import logging
import shutil
import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from nyx.paths import local_dir, roaming_dir

log = logging.getLogger(__name__)

KEEP = 3
INFO = "copia.json"


@dataclass(frozen=True, slots=True)
class DataFiles:
    """Dónde están los datos que se copian (las pruebas ponen carpetas suyas)."""

    roaming: Path
    local: Path

    @classmethod
    def default(cls) -> DataFiles:
        return cls(roaming_dir(), local_dir())

    def plain(self) -> list[Path]:
        return [
            self.roaming / "settings.json",
            self.roaming / "extensions.json",
            self.local / "game-queue.json",
            self.local / "settings-window.json",
        ]

    def databases(self) -> list[Path]:
        return [self.local / "alarms.db", self.local / "shortcuts.db"]

    @property
    def backups(self) -> Path:
        return self.local / "copias"


def _trash(path: Path) -> None:
    from send2trash import send2trash

    send2trash(str(path))


def make_backup(
    version: str, files: DataFiles | None = None, *, now: datetime | None = None
) -> Path:
    """Copia los datos y devuelve la carpeta de la copia."""
    files = files or DataFiles.default()
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    folder = files.backups / f"{stamp}-{version}"
    folder.mkdir(parents=True, exist_ok=False)
    copied: dict[str, str] = {}
    for src in files.plain():
        if src.exists():
            dst = folder / ("roaming" if src.parent == files.roaming else "local") / src.name
            dst.parent.mkdir(exist_ok=True)
            shutil.copy2(src, dst)
            copied[str(dst.relative_to(folder))] = str(src)
    for db in files.databases():
        if db.exists():
            dst = folder / "local" / db.name
            dst.parent.mkdir(exist_ok=True)
            # La copia de SQLite incluye lo que esté en el WAL: coherente aunque esté abierta.
            # `with sqlite3.connect()` no cierra la conexión: `closing` sí (en Windows, una
            # base abierta no se puede mover luego a la papelera).
            with closing(sqlite3.connect(db)) as source, closing(sqlite3.connect(dst)) as target:
                source.backup(target)
            copied[str(dst.relative_to(folder))] = str(db)
    (folder / INFO).write_text(
        json.dumps({"version": version, "files": copied}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("Copia de seguridad en %s (%d archivos)", folder, len(copied))
    return folder


def restore(folder: Path) -> list[Path]:
    """Vuelve a poner los datos de una copia. Devuelve lo restaurado."""
    info = json.loads((folder / INFO).read_text(encoding="utf-8"))
    done = []
    for rel, original in info["files"].items():
        src, dst = folder / rel, Path(original)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.suffix == ".db":
            # Los -wal y -shm de la base de ahora no valen para la copia: a la papelera.
            for extra in (dst.with_name(dst.name + "-wal"), dst.with_name(dst.name + "-shm")):
                if extra.exists():
                    _trash(extra)
        shutil.copy2(src, dst)
        done.append(dst)
    log.warning("Restaurada la copia %s", folder.name)
    return done


def prune(files: DataFiles | None = None, trash: Callable[[Path], None] | None = None) -> None:
    """Deja las `KEEP` copias más nuevas; las demás, a la papelera."""
    files = files or DataFiles.default()
    trash = trash or _trash
    if not files.backups.exists():
        return
    copies = sorted(p for p in files.backups.iterdir() if (p / INFO).exists())
    for old in copies[:-KEEP]:
        try:
            trash(old)
        except OSError:
            log.warning("No se pudo mandar a la papelera la copia %s", old, exc_info=True)
