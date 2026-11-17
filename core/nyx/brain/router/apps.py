"""Reglas de abrir y cerrar (apps, webs, carpetas, ajustes de Windows) y deshacer."""

from __future__ import annotations

import re

from nyx.brain.router.comun import (
    Miss,
    Route,
    _call,
    _fix_typo,
    _window_name,
    rule,
)
from nyx.index.aliases import normalize, strip_articles
from nyx.index.model import Kind
from nyx.index.service import SystemIndex
from nyx.tools.open_url import to_url


@rule(
    "undo",
    r"^(?:deshaz(?:lo)?|de[sz]h?a[sz]?t?lo|deshacer|deshaz eso|deshaz lo ultimo|vuelve atras|revierte(?:lo)?|anula(?:lo)?|anula eso|(?:recupera|restaura)(?:lo|la|los|las)?(?: (?:el|la|los|las) (?:archivos?|carpetas?|fotos?))?(?: de la papelera)?)$",
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
    name = _fix_typo(_window_name(target), index)  # «dis cord» (Whisper) → Discord (6.25)
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


# --- ajustes de Windows por lo que se quiere cambiar (6.25): «quiero cambiar el fondo de
# pantalla», «¿cómo cambio el idioma?», «llévame a los ajustes del bluetooth». Solo si lo
# nombrado es exactamente una página de Configuración. ---


def _exact_setting(raw: str, index: SystemIndex) -> str | None:
    bare = strip_articles(raw.strip())
    best = index.confident(index.resolve(bare, {Kind.SETTING}))
    return best.entry.name if best is not None and best.alias == bare else None


@rule(
    "settings_need",
    r"^(?:quiero|necesito|tengo que|como)\s+(?:cambiar|cambio|configurar|configuro|ajustar|ajusto)"
    r"\s+(?:el\s+|la\s+|los\s+|las\s+|mi\s+|mis\s+)?(?P<x>[a-z0-9 ]+)$"
    r"|^no\s+me\s+(?:va|funciona)\s+(?:el\s+|la\s+)?(?P<y>[a-z0-9 ]+?)\s+llevame\s+a\s+"
    r"(?:donde\s+se\s+configura|(?:sus|los)\s+ajustes)$"
    r"|^llevame\s+a\s+(?:los\s+ajustes|la\s+configuracion|las\s+opciones)\s+(?:de\s+la|del|de)\s+"
    r"(?P<z>[a-z0-9 ]+)$",
)
def _settings_need(m: re.Match[str], index: SystemIndex) -> Route | None:
    page = _exact_setting(m.group("x") or m.group("y") or m.group("z"), index)
    return _call("settings_need", "open_settings", page=page) if page else None


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
    # «ábreme el último documento que descargué» (ERRORES.md): buscarlo y abrirlo son dos
    # pasos, del LLM; no un nombre que no se encuentra.
    r"|\b(?:ultim[oa]s?|mas recientes?)\b"
    r"|\bque (?:descargue|me descargue|he descargado|me baje|guarde|he guardado|cree|he creado)\b"
)
_EXPLANATION = re.compile(r"\s+(?:que|para|porque|pa)\s+.+$")
_LO_DE = re.compile(r"^lo\s+del?\s+")
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
        # «arranca el Discord que voy a hablar con los colegas», «abre lo del bluetooth para
        # emparejar unos cascos» (6.25): sin la explicación de detrás, si así sí está claro.
        short = _EXPLANATION.sub("", _LO_DE.sub("", target)).strip()
        if short and short != target:
            best = index.confident(index.resolve(short, kinds))
    if best is None:
        return Miss(target, matches)
    tool, arg = _TOOL_FOR_KIND[best.entry.kind]
    value = best.entry.name if best.entry.kind is not Kind.FOLDER else best.entry.launch.value
    return _call("open", tool, **{arg: value})
