"""Selección de archivos común a list_files, move_files, copy_files y delete_files.

«los últimos 5 archivos de Descargas», «las imágenes del Escritorio», «los PDF de
Documentos», «el archivo factura de Descargas»… Nunca se selecciona «todo» sin pedirlo:
hace falta `all=true` explícito.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import Field
from rapidfuzz import fuzz

from nyx.index.aliases import normalize
from nyx.index.model import Kind
from nyx.tools.base import Params, ToolContext, ToolResult
from nyx.tools.resolve import pick

FileKind = Literal["images", "videos", "documents", "audio", "archives", "installers", "folders"]

EXTENSIONS: dict[str, frozenset[str]] = {
    "images": frozenset(
        [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".tif", ".tiff", ".svg", ".ico"]
    ),
    "videos": frozenset([".mp4", ".mkv", ".mov", ".avi", ".webm", ".wmv", ".m4v"]),
    "documents": frozenset(
        [
            ".pdf",
            ".doc",
            ".docx",
            ".odt",
            ".rtf",
            ".txt",
            ".md",
            ".xls",
            ".xlsx",
            ".ods",
            ".csv",
            ".ppt",
            ".pptx",
            ".odp",
        ]
    ),
    "audio": frozenset([".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".opus"]),
    "archives": frozenset([".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"]),
    "installers": frozenset([".exe", ".msi", ".msix", ".appx"]),
}
KIND_NAMES = {
    "images": "imágenes",
    "videos": "vídeos",
    "documents": "documentos",
    "audio": "audios",
    "archives": "comprimidos",
    "installers": "instaladores",
    "folders": "carpetas",
}
NAME_MATCH = 85
SUGGEST_MATCH = 60
MAX_ITEMS = 500
_EXPLORER_SUFFIX = re.compile(r"\s*-\s*(?:Explorador de archivos|File Explorer)$", re.I)


class FileSelection(Params):
    folder: str = Field(min_length=1, max_length=1000, description="Carpeta")
    names: list[str] | None = Field(default=None, max_length=50, description="Nombres")
    newest: int | None = Field(default=None, ge=1, le=MAX_ITEMS, description="Últimos N")
    kind: FileKind | None = Field(default=None, description="Tipo")
    extension: str | None = Field(default=None, max_length=10, description="Extensión")
    all: bool = Field(default=False, description="Todos")
    include_folders: bool = Field(default=False, description="Incluir carpetas")


def resolve_folder(ctx: ToolContext, target: str) -> Path | ToolResult:
    cleaned = _EXPLORER_SUFFIX.sub("", target).strip()
    path = Path(cleaned)
    if path.is_absolute():
        return path if path.is_dir() else ToolResult.fail(f"No existe la carpeta {path}")
    # «Imágenes/Fondos»: la primera parte se busca en el índice y el resto se añade tal cual
    # (las subcarpetas recién creadas en un plan aún no están indexadas).
    head, *rest = path.parts
    found = pick(ctx.index, head, {Kind.FOLDER}, "la carpeta")
    if isinstance(found, ToolResult):
        # Subcarpeta recién creada bajo una carpeta conocida (p. ej. Escritorio\Nueva carpeta)
        # antes de que vuelva a pasar el escáner.
        if head and head not in (".", ".."):
            for entry in ctx.index.entries({Kind.FOLDER}):
                root = Path(entry.launch.value)
                candidate = root / head / Path(*rest)
                if candidate.is_dir():
                    return candidate
        return found
    path = Path(found.entry.launch.value, *rest)
    if path.is_dir():
        return path
    return ToolResult.fail(f"No existe la carpeta {Path(found.entry.name, *rest)}")


def _matches_name(path: Path, wanted: str) -> bool:
    want = normalize(wanted)
    name, stem = normalize(path.name), normalize(path.stem)
    if want in (name, stem):
        return True
    return (
        want in name
        or fuzz.ratio(want, stem) >= NAME_MATCH
        or fuzz.token_sort_ratio(want, stem) >= NAME_MATCH
    )


def _closest_name(candidates: list[Path], names: list[str]) -> Path | None:
    best_score = 0.0
    best_path: Path | None = None
    for p in candidates:
        stem = normalize(p.stem)
        for wanted in names:
            want = normalize(wanted)
            score = max(float(fuzz.ratio(want, stem)), float(fuzz.token_sort_ratio(want, stem)))
            if score > best_score:
                best_score, best_path = score, p
    return best_path if best_score >= SUGGEST_MATCH else None


def select(sel: FileSelection, ctx: ToolContext) -> tuple[Path, list[Path]] | ToolResult:
    """(carpeta, elementos) según la selección. Se ejecuta en un hilo: toca el disco."""
    folder = resolve_folder(ctx, sel.folder)
    if isinstance(folder, ToolResult):
        return folder
    only_folders = sel.include_folders and not (
        sel.names or sel.newest or sel.kind or sel.extension or sel.all
    )
    if not (sel.names or sel.newest or sel.kind or sel.extension or sel.all or sel.include_folders):
        return ToolResult.fail("¿Qué archivos?", "dime cuáles, cuántos o de qué tipo")
    want_folders = sel.kind == "folders" or only_folders
    try:
        items = [
            p
            for p in folder.iterdir()
            if (
                p.is_dir()
                if want_folders
                else (p.is_file() or (sel.include_folders and p.is_dir()))
            )
            and not _hidden(p)
        ]
    except OSError as e:
        return ToolResult.fail(f"No puedo leer {folder.name}", str(e))
    candidates = list(items)
    if sel.kind and sel.kind != "folders":
        items = [p for p in items if p.suffix.lower() in EXTENSIONS[sel.kind]]
    if sel.extension:
        ext = "." + sel.extension.lower().lstrip(".")
        items = [p for p in items if p.suffix.lower() == ext]
    if sel.names:
        items = [p for p in items if any(_matches_name(p, n) for n in sel.names)]
    items.sort(key=_mtime, reverse=True)
    if sel.newest:
        items = items[: sel.newest]
    if not items:
        if sel.names and (hint_path := _closest_name(candidates, sel.names)) is not None:
            return ToolResult.fail(
                f"No hay archivos así en {folder.name}", f"¿quizá «{hint_path.name}»?"
            )
        what = "carpetas" if want_folders else "archivos"
        suffix = " así" if sel.names or sel.extension else ""
        return ToolResult.fail(f"No hay {what}{suffix} en {folder.name}")
    return folder, items[:MAX_ITEMS]


def _mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def _hidden(p: Path) -> bool:
    if p.name.startswith(".") or p.name.lower() in ("desktop.ini", "thumbs.db"):
        return True
    try:
        attrs = getattr(p.stat(), "st_file_attributes", 0)
    except OSError:
        return True
    return bool(attrs & 0x2 or attrs & 0x4)  # oculto o de sistema


def describe(items: list[Path], kind: str | None = None) -> str:
    """«5 archivos», «1 archivo», «3 imágenes», «la carpeta Fondos»."""
    if len(items) == 1:
        p = items[0]
        return f"la carpeta {p.name}" if p.is_dir() else f"«{p.name}»"
    noun = (
        "carpetas"
        if items and all(p.is_dir() for p in items)
        else KIND_NAMES.get(kind or "", "archivos")
    )
    return f"{len(items)} {noun}"


def preview(items: list[Path], limit: int = 3) -> str:
    names = [p.name for p in items[:limit]]
    more = f" y {len(items) - limit} más" if len(items) > limit else ""
    return ", ".join(names) + more


def unique_target(folder: Path, name: str) -> Path:
    """Destino libre: «foto.jpg», «foto (2).jpg»… Nunca se sobrescribe nada."""
    target = folder / name
    if not target.exists():
        return target
    stem, suffix = Path(name).stem, Path(name).suffix
    for i in range(2, 1000):
        candidate = folder / f"{stem} ({i}){suffix}"
        if not candidate.exists():
            return candidate
    raise OSError(f"demasiados archivos llamados {name}")
