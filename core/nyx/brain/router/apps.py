"""Reglas de abrir y cerrar (apps, webs, carpetas, ajustes de Windows) y deshacer."""

from __future__ import annotations

import re

from nyx.brain.router.comun import (
    Miss,
    Route,
    _call,
    _window_name,
    rule,
)
from nyx.index.model import Kind
from nyx.index.service import SystemIndex
from nyx.tools.open_url import to_url


@rule(
    "undo",
    r"^(?:deshaz(?:lo)?|deshacer|deshaz eso|deshaz lo ultimo|vuelve atras|revierte(?:lo)?|anula(?:lo)?|anula eso|(?:recupera|restaura)(?:lo|la|los|las)?(?: (?:el|la|los|las) (?:archivos?|carpetas?|fotos?))?(?: de la papelera)?)$",
)
def _undo(m: re.Match[str], _: SystemIndex) -> Route:
    return _call("undo", "undo")


@rule("close", r"^(?:cierra(?:me)?|cerrar)\s+(?P<x>.+)$")
def _close(m: re.Match[str], index: SystemIndex) -> Route | None:
    target = m.group("x")
    if target.startswith(("sesion", "la sesion", "el ordenador", "el pc")):
        return None  # cerrar sesión / apagar: system_power (fase 6)
    if re.match(
        r"^(?:(?:la|esta)\s+)?carpeta(?:\s+que\s+(?:tengo|hay))?\s+abierta$|^esta\s+carpeta$",
        target,
    ):
        return _call("close", "close_app", name="carpeta abierta")
    if mf := re.match(
        r"^(?:la\s+)?carpeta(?:\s+(?:llamada|que\s+se\s+llama|de\s+nombre))?\s+(?P<f>.+)$",
        target,
    ):
        return _call("close", "close_app", name=f"carpeta {mf.group('f')}")
    name = _window_name(target)
    return _call("close", "close_app", name=name)


# --- abrir (lo último: es el patrón más general) ---

_IN_BROWSER = re.compile(r"\s+en (?:el )?(?:navegador|chrome|edge|firefox|internet)$")
_SETTINGS_PREFIX = re.compile(
    r"^(?:(?:la|las|los)\s+)?(?:configuracion|ajustes|opciones)(?:\s+(?:del|de la|de los|de las|de))?(?:\s+|$)"
)
_FOLDER_PREFIX = re.compile(r"^(?:la\s+)?carpeta(?:\s+(?:del|de))?\s+")
_INDEFINITE = ("un ", "una ", "otro ", "otra ", "nuevo ", "nueva ", "algo ", "alguna ")
# Lo que señala a algo anterior y no es un nombre (Whisper oye «ábrela» como «abre la»).
_REFERENCE = re.compile(
    r"^(?:la|lo|las|los|eso|esto|esa|ese|esas|esos|ella|ello|aquello)$"
    r"|\bque (?:has|acabas de|me has) (?:creado|abierto|descargado|movido|copiado|encontrado)\b"
    r"|\bde antes\b|\b(?:la|lo) (?:anterior|ultim[oa])\b"
)
_TOOL_FOR_KIND = {
    Kind.APP: ("open_app", "name"),
    Kind.GAME: ("open_app", "name"),
    Kind.FOLDER: ("open_path", "target"),
    Kind.SETTING: ("open_settings", "page"),
    Kind.WEB: ("open_url", "target"),
}


@rule(
    "open",
    r"^(?:abre|abrir|abreme|abrime|lanza|lanzame|inicia|iniciame|ejecuta|arranca|entra en|ir a)\s+(?P<x>.+)$",
)
def _open(m: re.Match[str], index: SystemIndex) -> Route | Miss | None:
    target = m.group("x")
    if target.startswith(_INDEFINITE):
        return None  # «abre una pestaña nueva» no es un nombre: lo decide el LLM
    if _REFERENCE.search(target):
        return None  # «ábrela», «abre la que has creado»: el LLM, con la memoria corta
    kinds: set[Kind] | None = None
    if _IN_BROWSER.search(target):
        target, kinds = _IN_BROWSER.sub("", target), {Kind.WEB}
    elif _SETTINGS_PREFIX.match(target):
        page = _SETTINGS_PREFIX.sub("", target)
        return _call("open", "open_settings", page=page)
    elif _FOLDER_PREFIX.match(target):
        target, kinds = _FOLDER_PREFIX.sub("", target), {Kind.FOLDER}
    if to_url(target):
        return _call("open", "open_url", target=target)
    matches = index.resolve(target, kinds)
    best = index.confident(matches)
    if best is None:
        return Miss(target, matches)
    tool, arg = _TOOL_FOR_KIND[best.entry.kind]
    value = best.entry.name if best.entry.kind is not Kind.FOLDER else best.entry.launch.value
    return _call("open", tool, **{arg: value})
