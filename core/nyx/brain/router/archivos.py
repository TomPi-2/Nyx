"""Reglas de archivos y carpetas: crear, mover, copiar, borrar, buscar y listar."""

from __future__ import annotations

import re
from pathlib import Path

from nyx.brain.router.comun import (
    _N,
    _RAW,
    Miss,
    Route,
    _call,
    _original,
    parse_number,
    rule,
)
from nyx.index.model import Kind
from nyx.index.service import SystemIndex

_COUNT = rf"(?:(?P<n1>{_N})\s+)?(?:ultim[oa]s?|mas recientes?)(?:\s+(?P<n2>{_N}))?"
_WHAT = r"(?:\s+(?P<what>archivos?|ficheros?|fotos?|imagen(?:es)?|videos?|documentos?|pdfs?|capturas?|audios?|canciones|cancion|carpetas?|cosas))?"
_KIND_WORDS = {
    "fotos": "images",
    "imagenes": "images",
    "capturas": "images",
    "videos": "videos",
    "documentos": "documents",
    "audios": "audio",
    "canciones": "audio",
    "carpetas": "folders",
    "carpeta": "folders",
}


def _selection(m: re.Match[str]) -> dict[str, object] | None:
    """newest/kind/extension de «los últimos 5 archivos», «las 3 últimas fotos», «los pdf»…"""
    raw_n = m.group("n1") or m.group("n2")
    newest = parse_number(raw_n) if raw_n else 1
    if newest is None or not 1 <= newest <= 500:
        return None
    what = m.group("what") or ""
    out: dict[str, object] = {"newest": newest}
    kind = _KIND_WORDS.get(what) or _KIND_WORDS.get(what + "s") or _KIND_WORDS.get(what + "es")
    if kind:
        out["kind"] = kind
    elif what.startswith("pdf"):
        out["extension"] = "pdf"
    return out


def _raw_after(pattern: str) -> str | None:
    """Trozo del texto original (con mayúsculas) tras una palabra clave."""
    m = re.search(pattern, _RAW.get(), re.IGNORECASE)
    return m.group(1).strip(" «»\"'") if m else None


@rule(
    "create_folder",
    r"^(?:crea(?:me)?|crear|haz(?:me)?)\s+(?:una|la)\s+(?:nueva\s+)?carpeta(?:\s+nueva)?(?:\s+en\s+(?P<p1>.+?))?\s+(?:llamada|que se llame|con el nombre(?: de)?|de nombre)\s+(?P<name>.+?)(?:\s+en\s+(?P<p2>.+))?$",
)
def _create_folder(m: re.Match[str], _: SystemIndex) -> Route | None:
    name = _raw_after(
        r"(?:llamada|que se llame|con el nombre(?: de)?|de nombre)\s+(.+?)(?:\s+en\s+[^,]+)?$"
    )
    parent = m.group("p1") or m.group("p2") or "documentos"
    return _call("create_folder", "create_folder", name=name or m.group("name"), parent=parent)


@rule(
    "create_folder_named",
    r"^(?:crea(?:me)?|crear)\s+la\s+carpeta\s+(?P<name>.+?)(?:\s+en\s+(?P<p>.+))?$",
)
def _create_folder_named(m: re.Match[str], _: SystemIndex) -> Route | None:
    name = _raw_after(r"carpeta\s+(.+?)(?:\s+en\s+[^,]+)?$")
    return _call(
        "create_folder",
        "create_folder",
        name=name or m.group("name"),
        parent=m.group("p") or "documentos",
    )


@rule(
    "transfer",
    rf"^(?P<verb>mueve(?:me)?|pasa(?:me)?|lleva(?:me)?|copia(?:me)?)\s+(?:los|las|el|la)\s+{_COUNT}{_WHAT}\s+(?:de|del|desde)\s+(?:la carpeta\s+(?:de\s+)?)?(?P<src>.+?)\s+(?:a|al|hasta)\s+(?:la carpeta\s+(?:de\s+)?)?(?P<dst>.+)$",
)
def _transfer(m: re.Match[str], _: SystemIndex) -> Route | None:
    selection = _selection(m)
    if selection is None:
        return None
    tool = "copy_files" if m.group("verb").startswith("copia") else "move_files"
    return _call("transfer", tool, folder=m.group("src"), destination=m.group("dst"), **selection)


@rule(
    "transfer_named",
    r"^(?P<verb>mueve(?:me)?|pasa(?:me)?|copia(?:me)?)\s+(?:el|la)\s+(?:archivo|fichero|documento|foto|video)\s+(?P<name>.+?)\s+(?:de|del|desde)\s+(?P<src>.+?)\s+(?:a|al)\s+(?P<dst>.+)$",
)
def _transfer_named(m: re.Match[str], _: SystemIndex) -> Route:
    tool = "copy_files" if m.group("verb").startswith("copia") else "move_files"
    return _call(
        "transfer", tool, folder=m.group("src"), names=[m.group("name")], destination=m.group("dst")
    )


_DELETE = r"(?:borra(?:me)?|borrar|elimina(?:me)?|eliminar|(?:manda|tira|envia|mueve)(?:me)? a la papelera)"


@rule(
    "delete_folder",
    rf"^{_DELETE}\s+la\s+carpeta(?:\s+(?:llamada|que\s+se\s+llame|con\s+el\s+nombre(?:\s+de)?|de\s+nombre))?\s+(?P<x>.+?)(?:\s+(?:de|del|en)\s+(?:la\s+carpeta\s+(?:de\s+)?)?(?:el\s+|la\s+)?(?P<parent>.+))?$",
)
def _delete_folder(m: re.Match[str], index: SystemIndex) -> Route | Miss:
    name = _raw_after(
        r"carpeta(?:\s+(?:llamada|que\s+se\s+llame|con\s+el\s+nombre(?:\s+de)?|de\s+nombre))?\s+(.+?)(?:\s+(?:de|del|en)\s+[^,]+)?$"
    )
    raw_x = m.group("x")
    parent = m.group("parent")
    if parent:
        named_explicitly = bool(
            re.search(
                r"\bcarpeta\s+(?:llamada|que\s+se\s+llame|con\s+el\s+nombre|de\s+nombre)\b",
                m.group(0),
            )
        )
        if named_explicitly or index.confident(index.resolve(parent, {Kind.FOLDER})):
            clean_name = (name or raw_x).strip(" «»\"'")
            return _call(
                "delete",
                "delete_files",
                folder=parent,
                names=[clean_name],
                include_folders=True,
            )
        raw_x = f"{raw_x} {m.group(0).split(raw_x, 1)[1].strip()}"
    matches = index.resolve(raw_x, {Kind.FOLDER})
    best = index.confident(matches)
    if best is None:
        return Miss(raw_x, matches)
    path = Path(best.entry.launch.value)
    return _call(
        "delete", "delete_files", folder=str(path.parent), names=[path.name], include_folders=True
    )


@rule(
    "delete_folders",
    r"^(?:borra(?:me)?|borrar|elimina(?:me)?|elimino|eliminar|(?:manda|tira|envia|mueve)(?:me)?\s+a\s+la\s+papelera)\s+"
    r"(?:todas\s+)?las\s+carpetas(?:\s+que\s+hay)?\s+(?:dentro\s+de(?:l)?|de|del|en)\s+"
    r"(?:la\s+carpeta\s+(?:de\s+)?)?(?:el\s+|la\s+)?(?P<src>.+)$",
)
def _delete_folders(m: re.Match[str], index: SystemIndex) -> Route | None:
    src = m.group("src")
    if re.search(r"\b(?:que\s+(?:tengo|hay)\s+abierta|abierta|anterior|antes|esa|esta)\b", src):
        return None
    if index.confident(index.resolve(src, {Kind.FOLDER})) is None:
        return None
    return _call("delete_folders", "delete_files", folder=src, kind="folders", all=True)


@rule(
    "delete_files",
    rf"^{_DELETE}\s+(?:los|las|el|la)\s+{_COUNT}{_WHAT}\s+(?:de|del)\s+(?:la carpeta\s+(?:de\s+)?)?(?P<src>.+)$",
)
def _delete_files(m: re.Match[str], _: SystemIndex) -> Route | None:
    selection = _selection(m)
    if selection is None:
        return None
    return _call("delete", "delete_files", folder=m.group("src"), **selection)


@rule(
    "delete_named",
    rf"^{_DELETE}\s+(?:el|la)\s+(?:archivo|fichero|documento|foto|video)\s+(?P<name>.+?)\s+(?:de|del)\s+(?P<src>.+)$",
)
def _delete_named(m: re.Match[str], _: SystemIndex) -> Route:
    return _call("delete", "delete_files", folder=m.group("src"), names=[m.group("name")])


# Lo que se busca en internet aunque no se diga «en internet» (sin «archivo», «foto»… ni
# carpeta: «busca el pdf de la receta» sigue siendo un archivo).
_WEB_THING = re.compile(
    r"(?:receta|recetas|tutorial|tutoriales|instrucciones|informacion|noticias|significado|"
    r"definicion|letra de|pasos para|ideas para|trucos para|consejos para)\b"
)


@rule(
    "find",
    # \b tras el artículo y el «de»: sin él, «busca una receta» buscaba «a receta» (2026-11-13).
    r"^(?:busca(?:me)?|buscar|encuentra(?:me)?|donde esta(?:n)?)\s+(?:(?:el|la|los|las|un|una|mis|mi)\b)?\s*(?P<what>archivos?|ficheros?|documentos?|fotos?|imagen(?:es)?|videos?|pdfs?)?\s*(?:(?:del|de|que se llama|llamado|con)\b)?\s*(?P<q>.+?)(?:\s+en\s+(?P<f>(?!google|internet|la web|youtube).+))?$",
)
def _find(m: re.Match[str], index: SystemIndex) -> Route | None:
    if not m.group("what") and not m.group("f") and _WEB_THING.match(m.group("q")):
        # «busca una receta de lentejas», «búscame un tutorial de Excel»: no es un archivo.
        return _call("find", "web_search", query=_original(m.group("q")))
    folder = m.group("f")
    if (
        folder
        and index.confident(index.resolve(folder, {Kind.APP}))
        and not index.confident(index.resolve(folder, {Kind.FOLDER}))
    ):
        return None  # «busca un canal en Discord»: dentro de una app (LLM)
    if re.search(r"\ben (?:google|internet|la web|youtube)\b", m.group(0)):
        return None  # búsqueda web (fase 6)
    if re.match(
        r"(?:que|quien|quienes|cuando|donde|como|cual|cuales|cuanto|por que)\b", m.group("q")
    ):
        # «busca qué aplicaciones ha creado Tepnyx» es una pregunta, no un archivo
        # (ERRORES.md, 2026-11-11): el LLM, con web_search.
        return None
    what = (m.group("what") or "").rstrip("s")
    kind = {"foto": "images", "image": "images", "imagene": "images", "video": "videos"}.get(what)
    query = m.group("q")
    if what.startswith("pdf"):
        query += " .pdf"  # el nombre del archivo acaba en .pdf
    return _call("find", "find_files", query=query, kind=kind, folder=m.group("f"))


@rule(
    "list",
    rf"^(?:que hay en|que tengo en|(?:lista(?:me)?|ensename|muestrame|dime)\s+(?:los|las)\s+(?:{_COUNT}\s+)?(?:archivos|ficheros|cosas)\s+(?:de|del|en))\s+(?:la carpeta\s+(?:de\s+)?)?(?P<f>.+)$",
)
def _list(m: re.Match[str], _: SystemIndex) -> Route | None:
    if "portapapeles" in m.group("f"):
        return None
    raw_n = m.group("n1") or m.group("n2")
    newest = parse_number(raw_n) if raw_n else None
    return _call("list", "list_files", folder=m.group("f"), newest=newest)


@rule(
    "files_said",
    # 6.25: «¿tengo algo en el escritorio?», «dime qué he descargado últimamente».
    r"^tengo\s+algo\s+en\s+(?:el\s+|la\s+|mi\s+)?(?:carpeta\s+(?:de\s+)?)?(?P<f>[a-z ]+)$"
    r"|^(?P<dl>(?:dime\s+|ensename\s+)?que\s+(?:me\s+)?he\s+descargado"
    r"(?:\s+(?:ultimamente|hoy|antes|esta\s+semana))?)$",
)
def _files_said(m: re.Match[str], _: SystemIndex) -> Route | None:
    if m.group("dl"):
        return _call("files_said", "list_files", folder="Descargas", newest=5)
    folder = m.group("f").strip()
    if folder.startswith(("que ", "pendiente", "programado")):
        return None
    return _call("files_said", "list_files", folder=folder)


@rule(
    "web_search",
    # «busca en internet quién inventó la imprenta», «búscame en Google recetas de lentejas»,
    # «busca en Wikipedia Napoleón» (6.06). YouTube no: es una web que se abre.
    r"^(?:busca(?:me)?|buscar|mira)\s+en\s+(?:internet|google|la\s+web|wikipedia)\s+(?P<q>.+)$"
    r"|^(?:busca(?:me)?|mira)\s+(?P<q2>.+?)\s+en\s+(?:internet|google|la\s+web|wikipedia)$",
)
def _web_search(m: re.Match[str], __: SystemIndex) -> Route:
    query = _original(m.group("q") or m.group("q2"))
    return _call("web_search", "web_search", query=query)
