r"""Rutas protegidas y carpetas del usuario (SPEC sección 8).

- Nunca se modifican: C:\Windows, Archivos de programa, ProgramData, las raíces de los
  discos, las carpetas de Nyx y las propias carpetas principales del usuario (mover o
  borrar «Documentos» entero no es algo que deba hacer un asistente).
- «Dentro de las carpetas del usuario» = bajo su carpeta personal. Fuera de ella, las
  confirmaciones son solo con clic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from nyx.paths import local_dir, roaming_dir


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    return Path(value) if value else None


def system_roots() -> list[Path]:
    roots = [
        _env_path("SystemRoot") or Path(r"C:\Windows"),
        _env_path("ProgramFiles") or Path(r"C:\Program Files"),
        _env_path("ProgramFiles(x86)") or Path(r"C:\Program Files (x86)"),
        _env_path("PROGRAMDATA") or Path(r"C:\ProgramData"),
    ]
    return roots


def _norm(path: Path) -> Path:
    try:
        return path.resolve(strict=False)
    except OSError:
        return path.absolute()


@dataclass
class PathPolicy:
    """Qué rutas se pueden tocar. Se construye una vez al arrancar."""

    home: Path = field(default_factory=Path.home)
    protected_trees: list[Path] = field(default_factory=list)  # ni ellas ni lo de dentro
    protected_exact: list[Path] = field(default_factory=list)  # ellas sí; lo de dentro, no

    @classmethod
    def default(cls, user_folders: list[Path] | None = None) -> PathPolicy:
        trees = [*system_roots(), roaming_dir(), local_dir()]
        exact = [Path.home(), *(user_folders or [])]
        return cls(
            home=_norm(Path.home()),
            protected_trees=[_norm(p) for p in trees],
            protected_exact=[_norm(p) for p in exact],
        )

    def protected(self, path: Path) -> bool:
        p = _norm(path)
        if p.parent == p:  # raíz de un disco: C:\, D:\…
            return True
        if any(p == root or p.is_relative_to(root) for root in self.protected_trees):
            return True
        return any(p == exact for exact in self.protected_exact)

    def protected_target(self, path: Path) -> bool:
        """¿Se puede escribir aquí? Dentro de «Documentos» sí; en el sistema o en una raíz, no."""
        p = _norm(path)
        if p.parent == p or p.parent.parent == p.parent:  # C:\ o C:\algo
            return True
        return any(p == root or p.is_relative_to(root) for root in self.protected_trees)

    def inside_user(self, path: Path) -> bool:
        return _norm(path).is_relative_to(self.home)
