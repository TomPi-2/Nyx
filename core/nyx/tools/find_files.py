"""find_files: busca archivos por nombre en las carpetas del usuario (verde).

Motor: Everything si está instalado; si no, el índice de Windows (ver winapi/search.py).
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from pydantic import Field, model_validator

from nyx.index.scanners.folders import known_folders
from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult
from nyx.tools.files import EXTENSIONS, FileKind, preview, resolve_folder
from nyx.winapi import search


class FindFilesParams(Params):
    query: str = Field(default="", max_length=200, description="Parte del nombre")
    kind: FileKind | None = Field(default=None, description="Tipo")
    extension: str | None = Field(default=None, max_length=10, description="Extensión (pdf)")
    folder: str | None = Field(default=None, max_length=1000, description="Carpeta")
    limit: int = Field(default=10, ge=1, le=50)
    newest: bool = Field(default=False, description="Más recientes primero")

    @model_validator(mode="after")
    def needs_name_or_extension(self) -> FindFilesParams:
        if not self.query.strip() and not self.extension:
            raise ValueError("falta query (parte del nombre) o extension")
        return self

    @property
    def suffix(self) -> str | None:
        return "." + self.extension.lower().lstrip(".") if self.extension else None


# «la última factura que tengo» → buscar «factura», la más reciente primero (ERRORES.md,
# 2026-11-11: se buscaba un archivo llamado «ultima factura que tengo»).
_RECENT = re.compile(
    r"\b(?:[uú]ltim[oa]s?|m[aá]s recientes?|m[aá]s nuev[oa]s?|recientes?|nuev[oa]s?)\b"
)
_ONE = re.compile(r"\b(?:el|la)\s+(?:[uú]ltim[oa]|m[aá]s reciente)\b")
_FILLER = re.compile(
    r"\b(?:que\s+(?:tengo|tenga|he\s+\w+|me\s+\w+|hay)|tengo|alg[uú]n[oa]?s?|tod[oa]s?|"
    r"cualquier|alguna\s+vez)\b"
)


def clean_query(raw: str) -> tuple[str, bool, bool]:
    """(lo que buscar en el nombre, ¿los más recientes primero?, ¿solo uno?)"""
    text = raw.strip()
    newest = bool(_RECENT.search(text.lower()))
    only_one = bool(_ONE.search(text.lower()))
    text = _FILLER.sub(" ", _RECENT.sub(" ", text.lower()))
    words = [w for w in text.split() if w not in search.STOPWORDS]
    # «facturas» → «factura»: el nombre se compara por partes y «factura» encaja con ambas.
    words = [
        w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith("ss") else w for w in words
    ]
    return " ".join(words), newest, only_one


def none_found(query: str) -> str:
    """«No he encontrado ninguna factura», «…ningún contrato»."""
    last = query.split()[-1] if query.split() else query
    feminine = last.endswith(("a", "ión", "ion", "dad", "tud"))
    return f"No he encontrado {'ninguna' if feminine else 'ningún'} {query}"


def by_date(paths: list[Path]) -> list[Path]:
    """Del más reciente al más antiguo (los que ya no existen, al final)."""

    def mtime(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0

    return sorted(paths, key=mtime, reverse=True)


def search_roots() -> list[Path]:
    return [p for name, p in known_folders().items() if name != "Carpeta personal"]


class FindFiles(Tool[FindFilesParams]):
    name = "find_files"
    description = (
        "Busca archivos por nombre. Ej.: «busca el contrato en Documentos» "
        "(query=contrato, folder=Documentos)."
    )
    risk = Risk.GREEN
    game_policy = GamePolicy.ALLOWED
    category = Category.FILES
    params_model = FindFilesParams
    observe = True
    timeout_s = 15.0

    async def run(self, params: FindFilesParams, ctx: ToolContext) -> ToolResult:
        if params.folder:
            folder = await asyncio.to_thread(resolve_folder, ctx, params.folder)
            if isinstance(folder, ToolResult):
                return folder
            roots = [folder]
        else:
            roots = await asyncio.to_thread(search_roots)
        asked, newest, only_one = clean_query(params.query)
        newest = newest or params.newest
        # «los pdf» sin nombre: se busca por la extensión.
        query = asked or params.suffix or ""
        if not query:
            return ToolResult.fail("¿Qué archivo busco?", "dime parte de su nombre")
        found, engine = await asyncio.to_thread(search.search, query, roots, 50)
        if params.kind:
            found = [p for p in found if p.suffix.lower() in EXTENSIONS[params.kind]]
        if params.suffix:
            found = [p for p in found if p.suffix.lower() == params.suffix]
        if newest:
            found = await asyncio.to_thread(by_date, found)
        found = found[: 1 if only_one else params.limit]
        if not found:
            what = asked or f"archivo {params.suffix}"
            return ToolResult.fail(none_found(what), "prueba con otra palabra del nombre")
        display = found[0].name if len(found) == 1 else f"{len(found)} resultados"
        secondary = str(found[0].parent) if len(found) == 1 else preview(found)
        return ToolResult(
            ok=True,
            message=f"{len(found)} resultados para «{query}» ({engine})",
            display=display,
            secondary=secondary,
            data={"paths": [str(p) for p in found], "engine": engine},
        )
