"""Selección de archivos común a list_files, move_files, copy_files y delete_files.

«los últimos 5 archivos de Descargas», «las imágenes del Escritorio», «los PDF de
Documentos», «el archivo factura de Descargas»… Nunca se selecciona «todo» sin pedirlo:
hace falta `all=true` explícito.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from rapidfuzz import fuzz

from nyx.index.aliases import normalize
from nyx.index.model import Kind
from nyx.tools.base import Params, ToolContext, ToolResult
from nyx.tools.resolve import pick

FileKind = Literal["images", "videos", "documents", "audio", "archives", "installers"]

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
}
NAME_MATCH = 85
MAX_ITEMS = 500


class FileSelection(Params):
    folder: str = Field(
        min_length=1, max_length=1000, description="Carpeta de origen (Descargas, Escritorio…)"
    )
    names: list[str] | None = Field(
        default=None, max_length=50, description="Nombres de archivos concretos (o parte)"
    )
    newest: int | None = Field(
        default=None, ge=1, le=MAX_ITEMS, description="Solo los N más recientes"
    )
    kind: FileKind | None = Field(default=None, description="Solo de este tipo")
    extension: str | None = Field(default=None, max_length=10, description="p. ej. pdf")
    all: bool = Field(default=False, description="Todos los archivos de la carpeta")
    include_folders: bool = Field(default=False, description="Incluir también subcarpetas")


def resolve_folder(ctx: ToolContext, target: str) -> Path | ToolResult:
    path = Path(target)
    if path.is_absolute():
        return path if path.is_dir() else ToolResult.fail(f"No existe la carpeta {path}")
    # «Imágenes/Fondos»: la primera parte se busca en el índice y el resto se añade tal cual
    # (las subcarpetas recién creadas en un plan aún no están indexadas).
    head, *rest = path.parts
    found = pick(ctx.index, head, {Kind.FOLDER}, "la carpeta")
    if isinstance(found, ToolResult):
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
    return want in name or fuzz.ratio(want, stem) >= NAME_MATCH


def select(sel: FileSelection, ctx: ToolContext) -> tuple[Path, list[Path]] | ToolResult:
    """(carpeta, elementos) según la selección. Se ejecuta en un hilo: toca el disco."""
    folder = resolve_folder(ctx, sel.folder)
    if isinstance(folder, ToolResult):
        return folder
    if not (sel.names or sel.newest or sel.kind or sel.extension or sel.all):
        return ToolResult.fail("¿Qué archivos?", "dime cuáles, cuántos o de qué tipo")
    try:
        items = [
            p
            for p in folder.iterdir()
            if (p.is_file() or (sel.include_folders and p.is_dir())) and not _hidden(p)
        ]
    except OSError as e:
        return ToolResult.fail(f"No puedo leer {folder.name}", str(e))
    if sel.kind:
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
        return ToolResult.fail(f"No hay archivos así en {folder.name}")
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
    noun = KIND_NAMES.get(kind or "", "archivos")
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
