"""Parte común de move_files y copy_files: qué se mueve, adónde y con qué nombres.

Nunca se sobrescribe: si ya existe un archivo con ese nombre, se usa «nombre (2)».
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from pydantic import Field

from nyx.tools.base import Prepared, ToolContext, ToolResult
from nyx.tools.files import FileSelection, describe, preview, resolve_folder, select, unique_target

log = logging.getLogger(__name__)


class TransferParams(FileSelection):
    destination: str = Field(
        min_length=1, max_length=1000, description="Carpeta de destino (Documentos, Fondos…)"
    )


@dataclass(frozen=True, slots=True)
class Plan:
    source: Path
    destination: Path
    items: list[Path]


async def plan(params: TransferParams, ctx: ToolContext, verb: str) -> Prepared:
    found = await asyncio.to_thread(select, params, ctx)
    if isinstance(found, ToolResult):
        return Prepared("", error=found)
    source, items = found
    dest = await asyncio.to_thread(resolve_folder, ctx, params.destination)
    if isinstance(dest, ToolResult):
        return Prepared("", error=dest)
    if dest == source:
        return Prepared("", error=ToolResult.fail("El origen y el destino son la misma carpeta"))
    if any(dest == p or dest.is_relative_to(p) for p in items if p.is_dir()):
        return Prepared("", error=ToolResult.fail("No puedo meter una carpeta dentro de sí misma"))
    what = describe(items, params.kind)
    return Prepared(
        summary=f"{verb} {what} de {source.name} a {dest.name}",
        detail=preview(items),
        paths=items if verb == "Mover" else [],
        targets=[dest],
        count=len(items),
        payload=Plan(source, dest, items),
    )


def move_all(pairs: list[tuple[Path, Path]]) -> list[tuple[Path, Path]]:
    done = []
    for src, dst in pairs:
        try:
            shutil.move(str(src), str(dst))
            done.append((src, dst))
        except OSError:
            log.warning("No se pudo mover %s", src, exc_info=True)
    return done


def copy_all(pairs: list[tuple[Path, Path]]) -> list[tuple[Path, Path]]:
    done = []
    for src, dst in pairs:
        try:
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            done.append((src, dst))
        except OSError:
            log.warning("No se pudo copiar %s", src, exc_info=True)
    return done


def targets(items: list[Path], dest: Path) -> list[tuple[Path, Path]]:
    pairs = []
    for item in items:
        target = unique_target(dest, item.name)
        # Reserva el nombre para que dos archivos iguales no reciban el mismo «(2)».
        pairs.append((item, target))
    taken: set[Path] = set()
    fixed = []
    for src, dst in pairs:
        while dst in taken:
            dst = unique_target(dest, f"{dst.stem} (copia){dst.suffix}")
        taken.add(dst)
        fixed.append((src, dst))
    return fixed
