"""Las extensiones oficiales que vienen con Nyx (OBS, Spotify…; tarea 7.14).

Hasta que exista la tienda (1.0), las de Tepnyx van dentro de Nyx y se ofrecen en Ajustes →
Extensiones («De Tepnyx»), sin instalar: el usuario elige cuáles quiere y ve sus permisos antes,
como con cualquier otra.

- **Nyx instalado:** `core\\extensiones\\*.nyxext`, empaquetadas y firmadas por
  `scripts/pack_official.py` al hacer la versión.
- **En desarrollo:** se empaquetan al vuelo desde `extensions/` del repositorio, sin firmar
  (para instalarlas hace falta el modo desarrollador, y salen «Sin revisar»).

`pack_folder` es lo mismo que hace `nyx_ext.py pack`: lo que no va en un paquete se queda fuera
y el resultado pasa las comprobaciones de instalar antes de darse por bueno.
"""

from __future__ import annotations

import logging
import os
import zipfile
from pathlib import Path

from nyx.ext.manifest import MANIFEST_NAME
from nyx.ext.store import PACKAGE_SUFFIX, PackageError, read_package
from nyx.paths import local_dir

log = logging.getLogger(__name__)

SKIP = frozenset(
    {
        ".git",
        "__pycache__",
        ".venv",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".DS_Store",
        "Thumbs.db",
    }
)
#: Lo que no va en el paquete aunque esté en la carpeta (en su raíz).
NOT_PACKED = frozenset({"tests", "pyproject.toml", "uv.lock", "ruff.toml"})


def pack_folder(folder: Path, out: Path) -> Path:
    """Empaqueta `folder` en `out` (sin firmar). Lanza PackageError si no valdría."""
    tmp = out.with_name(out.name + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(folder.rglob("*")):
            rel = path.relative_to(folder)
            if (
                path.is_file()
                and not SKIP.intersection(rel.parts)
                and rel.parts[0] not in NOT_PACKED
                and rel.name != "signature"
            ):
                zf.write(path, rel.as_posix())
    try:
        read_package(tmp)  # las mismas comprobaciones que al instalar
    except PackageError:
        _trash(tmp)
        raise
    os.replace(tmp, out)
    return out


def _code_root() -> Path:
    # nyx/ext/official.py → la carpeta que contiene `nyx` (core/ en desarrollo, core/app/
    # en Nyx instalado).
    return Path(__file__).resolve().parents[2]


def packaged_dir() -> Path | None:
    root = _code_root()
    if root.name == "app" and (root.parent / "extensiones").is_dir():
        return root.parent / "extensiones"
    return None


def source_dir() -> Path | None:
    repo = _code_root().parent / "extensions"
    return repo if repo.is_dir() else None


def packages(cache: Path | None = None) -> list[Path]:
    """Los `.nyxext` oficiales que se pueden ofrecer, de la versión instalada o del repositorio."""
    if (found := packaged_dir()) is not None:
        return sorted(found.glob(f"*{PACKAGE_SUFFIX}"))
    source = source_dir()
    if source is None:
        return []
    cache = cache or local_dir() / "ext-dev" / "oficiales"
    cache.mkdir(parents=True, exist_ok=True)
    out = []
    for folder in sorted(p.parent for p in source.glob(f"*/{MANIFEST_NAME}")):
        target = cache / f"{folder.name}{PACKAGE_SUFFIX}"
        newest = max(p.stat().st_mtime for p in folder.rglob("*") if p.is_file())
        try:
            if not target.exists() or target.stat().st_mtime < newest:
                pack_folder(folder, target)
            out.append(target)
        except (PackageError, OSError) as e:
            log.warning("Extensión oficial %s: no se puede empaquetar: %s", folder.name, e)
    return out


def _trash(path: Path) -> None:
    from send2trash import send2trash

    try:
        send2trash(str(path))
    except OSError as e:
        log.debug("No se pudo mandar %s a la papelera: %s", path, e)
