"""Migraciones versionadas al arrancar una versión nueva (SPEC §15).

Cada migración dice a partir de qué versión hace falta. Al arrancar, si la versión que se usó
la última vez (`version.json`) es más vieja que la actual, se hace una copia de los datos, se
aplican en orden las migraciones de ese tramo y se apunta la versión nueva. Si una falla, se
restaura la copia y Nyx sigue con los datos de antes (y lo dice el registro).

Hoy no hay ninguna: la lista empieza vacía y cada versión que cambie datos añade la suya.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from nyx.update.backup import DataFiles, make_backup, prune, restore

log = logging.getLogger(__name__)

Version = tuple[int, int, int]


def parse_version(text: str) -> Version:
    """«1.10.0» → (1, 10, 0): se compara número a número, nunca como texto."""
    parts = text.strip().lstrip("v").split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(f"versión no válida: {text!r}")
    major, minor, patch = (int(p) for p in parts)
    return major, minor, patch


@dataclass(frozen=True, slots=True)
class Migration:
    since: str  # la primera versión que necesita este cambio
    what: str  # para el registro
    run: Callable[[DataFiles], None]


#: Las migraciones de Nyx, en orden. Cada una debe poder repetirse sin estropear nada.
MIGRATIONS: tuple[Migration, ...] = ()


def last_version(files: DataFiles) -> str | None:
    try:
        data = json.loads((files.local / "version.json").read_text(encoding="utf-8"))
        return str(data["version"])
    except OSError, ValueError, KeyError, TypeError:
        return None


def _remember(files: DataFiles, version: str) -> None:
    files.local.mkdir(parents=True, exist_ok=True)
    (files.local / "version.json").write_text(json.dumps({"version": version}), encoding="utf-8")


@dataclass(frozen=True, slots=True)
class Outcome:
    applied: tuple[str, ...] = ()
    restored: bool = False
    error: str = ""
    #: Se viene de esta versión (más antigua): Nyx dice «Actualizada a la …» al arrancar.
    updated_from: str | None = None


def migrate(
    current: str,
    files: DataFiles | None = None,
    migrations: Sequence[Migration] = MIGRATIONS,
) -> Outcome:
    """Pone los datos al día para la versión `current`."""
    files = files or DataFiles.default()
    before = last_version(files)
    if before is None:  # primera vez (o se perdió el archivo): nada que migrar
        _remember(files, current)
        return Outcome()
    old, new = parse_version(before), parse_version(current)
    if new <= old:
        if new < old:
            log.warning(
                "Se ha vuelto de la %s a la %s: los datos se quedan como están", before, current
            )
            _remember(files, current)
        return Outcome()
    pending = [m for m in migrations if old < parse_version(m.since) <= new]
    if not pending:
        _remember(files, current)
        return Outcome(updated_from=before)
    backup = make_backup(before, files)
    applied: list[str] = []
    for migration in sorted(pending, key=lambda m: parse_version(m.since)):
        try:
            migration.run(files)
        except Exception as e:  # cualquier fallo: los datos de antes
            log.exception("Migración «%s» fallida: se restaura la copia", migration.what)
            restore(backup)
            return Outcome(
                tuple(applied), restored=True, error=f"{migration.what}: {e}", updated_from=before
            )
        applied.append(migration.what)
        log.info("Migración aplicada: %s", migration.what)
    _remember(files, current)
    prune(files)
    return Outcome(tuple(applied), updated_from=before)
