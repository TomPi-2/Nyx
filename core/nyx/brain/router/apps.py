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
from nyx.index.aliases import normalize, strip_articles
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


# --- abrir por lo que se necesita (6.25): «necesito la calculadora», «vamos a jugar al lol» ---
# Solo si el nombre coincide EXACTO con una app o un juego del equipo; si no, al LLM.

# Nombres de apps de Windows que también son palabras corrientes: sin artículo no se abren
# («necesito ayuda», «quiero música», «necesito notas»).
_GENERIC = frozenset(
    {
        "ayuda", "tiempo", "musica", "fotos", "camara", "correo", "mapas", "reloj", "notas",
        "noticias", "juegos", "tienda", "calendario", "contactos", "personas", "consejos",
        "alarmas", "configuracion", "ajustes", "internet", "telefono", "recortes", "tiempo libre",
    }
)  # fmt: skip
_WITH_ARTICLE = re.compile(r"^(?:el|la|los|las)\s")
_FOR_TAIL = re.compile(r"\s+para\s+.+$")


def _exact_app(raw: str, index: SystemIndex) -> str | None:
    """Nombre de la app o el juego que se llama exactamente `raw` (texto ya limpio), o None."""
    raw = _FOR_TAIL.sub("", raw.strip())
    bare = strip_articles(raw)
    if not bare or (bare in _GENERIC and not _WITH_ARTICLE.match(raw)):
        return None
    best = index.confident(index.resolve(raw, {Kind.APP, Kind.GAME}))
    if best is None or best.alias != bare:
        return None
    return best.entry.name


_LEAD = r"(?:tengo que|necesito|quiero|voy a|vamos a|me toca|toca|hay que|debo|me apetece)"


@rule(
    "open_game",
    r"^(?:hoy\s+)?(?:vamos a|voy a|quiero|me apetece|nos echamos|echamos|toca|me toca)\s+"
    r"(?:jugar|echar\s+(?:una|unas|otra)\s+partidas?|echar\s+un\s+rato|un\s+rato)\s+"
    r"(?:al|a la|a los|a|de)\s+(?P<x>.+)$",
)
def _open_game(m: re.Match[str], index: SystemIndex) -> Route | None:
    name = _exact_app(m.group("x"), index)
    return _call("open_game", "open_app", name=name) if name else None


# Tarea → apps que la hacen, por orden de preferencia (la primera instalada).
_TASKS: tuple[tuple[re.Pattern[str], tuple[str, ...]], ...] = tuple(
    (re.compile(rf"^{_LEAD}\s+(?:{pattern})(?:\s+para\s+.+)?$"), apps)
    for pattern, apps in (
        (
            r"(?:hacer|preparar|crear|montar)\s+(?:una\s+|unas\s+)?"
            r"(?:hojas?\s+de\s+calculo|tablas?\s+de\s+excel)",
            ("Excel", "LibreOffice Calc"),
        ),
        (
            r"(?:hacer|preparar|crear|montar)\s+(?:una\s+|unas\s+)?(?:presentacion(?:es)?|diapositivas)",
            ("PowerPoint", "LibreOffice Impress"),
        ),
        (
            r"(?:redactar|escribir|hacer|crear)\s+(?:un\s+)?(?:documento|trabajo\s+escrito|informe)",
            ("Word", "LibreOffice Writer"),
        ),
        (
            r"hacer\s+(?:unas\s+|una\s+)?(?:cuentas|operacion(?:es)?|calculos?)"
            r"|calcular\s+(?:una\s+cosa|algo)",
            ("Calculadora",),
        ),
        (
            r"grabar\s+(?:la\s+pantalla|la\s+partida|un\s+directo)|hacer\s+(?:un\s+)?directo|streamear",
            ("OBS Studio",),
        ),
        (
            r"(?:recortar|editar|retocar)\s+(?:una\s+|la\s+|esta\s+)?(?:foto|imagen|captura)"
            r"|dibujar(?:\s+algo)?",
            ("Paint",),
        ),
    )
)


@rule("open_task", rf"^{_LEAD}\s+.+$")
def _open_task(m: re.Match[str], index: SystemIndex) -> Route | None:
    text = m.group(0)
    for pattern, apps in _TASKS:
        if pattern.match(text):
            for app in apps:
                if name := _exact_app(normalize(app), index):
                    return _call("open_task", "open_app", name=name)
            return None  # se entiende la tarea, pero no hay app para ella: el LLM lo explica
    return None


@rule("open_with", rf"^{_LEAD}\s+(?P<what>.+?)\s+con\s+(?:el\s+|la\s+)?(?P<x>.+)$")
def _open_with(m: re.Match[str], index: SystemIndex) -> Route | None:
    """«quiero grabar un vídeo con el OBS»: la app que se nombra (solo si existe tal cual)."""
    name = _exact_app(m.group("x"), index)
    return _call("open_with", "open_app", name=name) if name else None


@rule(
    "open_need",
    # Las formas largas antes: «quiero usar X» no es «quiero» + «usar X».
    r"^(?:quiero usar|quiero abrir|necesito usar|necesito abrir|necesito|me hace falta|"
    r"me falta|quiero)\s+(?P<x>.+)$",
)
def _open_need(m: re.Match[str], index: SystemIndex) -> Route | None:
    name = _exact_app(m.group("x"), index)
    return _call("open_need", "open_app", name=name) if name else None


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
