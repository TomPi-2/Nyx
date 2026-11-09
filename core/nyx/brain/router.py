"""Router rápido, nivel 1 del cerebro (SPEC sección 6): frases frecuentes → herramienta, sin LLM.

Solo actúa si está seguro. Si el patrón encaja pero el nombre no se resuelve con claridad,
lo dice (`Miss`) para que el pipeline explique «no encuentro X»; en el bloque 3c esos casos
pasarán al LLM con los candidatos como pista.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path

from nyx.executor import ToolCall
from nyx.index.aliases import normalize
from nyx.index.model import Kind
from nyx.index.service import Match, SystemIndex
from nyx.stt.normalize import NUMBER_WORDS
from nyx.tools.open_url import to_url


@dataclass(frozen=True, slots=True)
class Route:
    calls: list[ToolCall]
    rule: str


@dataclass(frozen=True, slots=True)
class Miss:
    """El patrón encaja («abre X») pero X no se encuentra o es ambiguo."""

    target: str
    candidates: list[Match] = field(default_factory=list)


_TENS = {"sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90, "cien": 100}


def parse_number(text: str) -> int | None:
    text = text.strip()
    if text.isdigit():
        return int(text)
    if text in _TENS:
        return _TENS[text]
    if text in NUMBER_WORDS:
        return NUMBER_WORDS[text]
    for word, tens in _TENS.items():
        if text.startswith(f"{word} y "):
            unit = NUMBER_WORDS.get(text.removeprefix(f"{word} y "))
            if unit is not None and 1 <= unit <= 9:
                return tens + unit
    return None


_NUM = r"(?P<n>\d{1,3}|[a-z]+(?: y [a-z]+)?)"
_POLITE = re.compile(r"\s+(?:por favor|porfa|gracias)$")
_THIS_WINDOW = {"", "esta ventana", "la ventana", "esto", "esta", "la ventana activa"}


_DOMAIN_DOT = re.compile(r"(?<=\w)\.(?=(?:com|es|org|net|io|ai|tv|dev|app|gg|co|eu|me)\b)", re.I)
_VERBS = r"abre|abrir|pon|cierra|sube|baja|haz|hazme|mueve|crea|escribe|busca|silencia|pausa|cambia|maximiza|minimiza|lanza"
_SEVERAL_ACTIONS = re.compile(rf"\s(?:y|y luego|luego|despues|y despues)\s+(?:{_VERBS})\b")


_BACKGROUND = re.compile(
    r"\s+(?:en segundo plano|de fondo|por detras|sin enfocar(?:lo|la)?|sin el foco|"
    r"sin ponerl[oa] delante|sin traerl[oa] al frente|sin cambiar(?:me)? de ventana|"
    r"sin quitarme (?:la ventana|el foco)|minimizad[oa])(?=\s|$)"
)
_OPENERS = {"open_app", "open_url", "open_path", "open_settings"}


def _clean(text: str) -> str:
    return _POLITE.sub("", normalize(text)).strip()


_RAW: ContextVar[str] = ContextVar("router_raw", default="")

Handler = Callable[[re.Match[str], SystemIndex], "Route | Miss | None"]
_RULES: list[tuple[str, re.Pattern[str], Handler]] = []


def rule(name: str, pattern: str) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        _RULES.append((name, re.compile(pattern), fn))
        return fn

    return deco


def route(text: str, index: SystemIndex) -> Route | Miss | None:
    """Ruta para `text`, `Miss` si el patrón encaja sin destino claro, o None (→ LLM)."""
    _RAW.set(text.strip().rstrip(".!¡?¿ "))
    # «marca.com» → «marca punto com»: la limpieza quita los puntos; open_url los recupera.
    clean = _clean(_DOMAIN_DOT.sub(" punto ", text))
    if _SEVERAL_ACTIONS.search(clean):
        return None  # «abre el bloc de notas y abre una pestaña»: plan de varios pasos (LLM)
    # «abre Discord en segundo plano»: se abre sin quitarle el foco a la ventana actual.
    background = bool(_BACKGROUND.search(clean))
    clean = _BACKGROUND.sub("", clean).strip()
    for _, pattern, handler in _RULES:
        if m := pattern.match(clean):
            result = handler(m, index)
            if result is None:
                continue
            if background and isinstance(result, Route):
                for call in result.calls:
                    if call.name in _OPENERS:
                        call.arguments["focus"] = False
            return result
    return None


def _call(rule_name: str, tool: str, **arguments: object) -> Route:
    return Route([ToolCall(tool, {k: v for k, v in arguments.items() if v is not None})], rule_name)


# --- volumen (antes que «pon …» y «abre …») ---


@rule(
    "volume_up",
    rf"^(?:sube|subir|subeme|aumenta)\s+(?:el\s+)?(?:volumen|sonido)(?:\s+(?:a|al|hasta(?:\s+el)?)\s+{_NUM})?(?P<much>\s+mucho)?(?:\s+un poco)?$",
)
def _volume_up(m: re.Match[str], _: SystemIndex) -> Route | None:
    if m.group("n"):
        level = parse_number(m.group("n"))
        return _call("volume_up", "set_volume", level=level) if level is not None else None
    return _call("volume_up", "set_volume", change=20 if m.group("much") else 10)


@rule(
    "volume_down",
    rf"^(?:baja|bajar|bajame|reduce)\s+(?:el\s+)?(?:volumen|sonido)(?:\s+(?:a|al|hasta(?:\s+el)?)\s+{_NUM})?(?P<much>\s+mucho)?(?:\s+un poco)?$",
)
def _volume_down(m: re.Match[str], _: SystemIndex) -> Route | None:
    if m.group("n"):
        level = parse_number(m.group("n"))
        return _call("volume_down", "set_volume", level=level) if level is not None else None
    return _call("volume_down", "set_volume", change=-20 if m.group("much") else -10)


@rule(
    "volume_set",
    rf"^(?:(?:pon|deja|ajusta|cambia)\s+(?:el\s+)?)?volumen\s+(?:a|al|en)?\s*{_NUM}(?:\s*%|\s+por ciento)?$",
)
def _volume_set(m: re.Match[str], _: SystemIndex) -> Route | None:
    level = parse_number(m.group("n"))
    if level is None or level > 100:
        return None
    return _call("volume_set", "set_volume", level=level)


@rule(
    "unmute",
    r"^(?:quita(?:r)? el silencio|activa(?:r)? el sonido|desilencia|desmutea|devuelve el sonido|pon(?: el)? sonido)$",
)
def _unmute(m: re.Match[str], _: SystemIndex) -> Route:
    return _call("unmute", "set_volume", mute=False)


@rule(
    "mute",
    r"^(?:silencia(?:lo|r)?|mutea|silencio|quita(?:r)? el sonido|calla el (?:pc|ordenador))(?:\s+(?P<app>.+))?$",
)
def _mute(m: re.Match[str], index: SystemIndex) -> Route | None:
    app = m.group("app")
    if app in (None, "todo", "el pc", "el ordenador", "el sonido"):
        return _call("mute", "set_volume", mute=True)
    best = index.confident(index.resolve(app, {Kind.APP, Kind.GAME}))
    return _call("mute", "set_volume", mute=True, app=best.entry.name) if best else None


# --- multimedia ---


@rule(
    "media_pause",
    r"^(?:pausa|pausar|para|parar|deten|pausa la|para la)(?:\s+(?:la\s+|el\s+)?(?:musica|cancion|video|reproduccion|spotify))?$",
)
def _pause(m: re.Match[str], _: SystemIndex) -> Route:
    return _call("media_pause", "media_control", action="play_pause")


@rule(
    "media_play",
    r"^(?:reanuda|reanudar|continua|play|dale al play|reproduce|quita la pausa)(?:\s+(?:la\s+|el\s+)?(?:musica|cancion|video))?$",
)
def _play(m: re.Match[str], _: SystemIndex) -> Route:
    return _call("media_play", "media_control", action="play_pause")


@rule(
    "media_next",
    r"^(?:(?:pon\s+)?(?:la\s+)?siguiente|pasa(?:\s+de)?|salta|skip)(?:\s+(?:cancion|tema|pista|video))?$",
)
def _next(m: re.Match[str], _: SystemIndex) -> Route:
    return _call("media_next", "media_control", action="next")


@rule(
    "media_previous",
    r"^(?:(?:pon\s+)?(?:la\s+)?anterior|(?:cancion|tema|pista) anterior|vuelve a la anterior)(?:\s+(?:cancion|tema|pista))?$",
)
def _previous(m: re.Match[str], _: SystemIndex) -> Route:
    return _call("media_previous", "media_control", action="previous")


# --- capturas ---


@rule(
    "screenshot",
    r"^(?:(?:haz(?:me)?|saca(?:me)?|toma)\s+(?:una?\s+)?)?(?:captura|screenshot|pantallazo)(?:\s+de\s+pantalla)?(?P<rest>.*)$",
)
def _screenshot(m: re.Match[str], _: SystemIndex) -> Route:
    rest = m.group("rest")
    if re.search(r"principal", rest):
        target = "primary"
    elif re.search(r"tod[oa]s?|los dos|ambos|las dos", rest):
        target = "all"
    elif re.search(r"ventana", rest):
        target = "window"
    else:
        target = "current"
    return _call("screenshot", "screenshot", target=target)


# --- deshacer, cerrar y archivos (bloque 3b) ---

_NUMWORD = "|".join(sorted([*NUMBER_WORDS, *_TENS], key=len, reverse=True))
_N = rf"\d{{1,3}}|(?:{_NUMWORD})(?: y (?:{_NUMWORD}))?"
_COUNT = rf"(?:(?P<n1>{_N})\s+)?(?:ultim[oa]s?|mas recientes?)(?:\s+(?P<n2>{_N}))?"
_WHAT = r"(?:\s+(?P<what>archivos?|ficheros?|fotos?|imagen(?:es)?|videos?|documentos?|pdfs?|capturas?|audios?|canciones|cancion|cosas))?"
_KIND_WORDS = {
    "fotos": "images",
    "imagenes": "images",
    "capturas": "images",
    "videos": "videos",
    "documentos": "documents",
    "audios": "audio",
    "canciones": "audio",
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
    name = _window_name(target)
    return _call("close", "close_app", name=name)


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


@rule("delete_folder", rf"^{_DELETE}\s+la\s+carpeta\s+(?P<x>.+)$")
def _delete_folder(m: re.Match[str], index: SystemIndex) -> Route | Miss:
    matches = index.resolve(m.group("x"), {Kind.FOLDER})
    best = index.confident(matches)
    if best is None:
        return Miss(m.group("x"), matches)
    path = Path(best.entry.launch.value)
    return _call(
        "delete", "delete_files", folder=str(path.parent), names=[path.name], include_folders=True
    )


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


@rule(
    "find",
    r"^(?:busca(?:me)?|buscar|encuentra(?:me)?|donde esta(?:n)?)\s+(?:el|la|los|las|un|una|mis|mi)?\s*(?P<what>archivos?|ficheros?|documentos?|fotos?|imagen(?:es)?|videos?|pdfs?)?\s*(?:de|del|que se llama|llamado|con)?\s*(?P<q>.+?)(?:\s+en\s+(?P<f>(?!google|internet|la web|youtube).+))?$",
)
def _find(m: re.Match[str], _: SystemIndex) -> Route | None:
    if re.search(r"\ben (?:google|internet|la web|youtube)\b", m.group(0)):
        return None  # búsqueda web (fase 6)
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
    raw_n = m.group("n1") or m.group("n2")
    newest = parse_number(raw_n) if raw_n else None
    return _call("list", "list_files", folder=m.group("f"), newest=newest)


# --- ventanas ---


def _window_name(raw: str | None) -> str | None:
    raw = (raw or "").strip()
    return None if raw in _THIS_WINDOW else raw


@rule(
    "window_state",
    r"^(?P<verb>maximiza|maximizar|minimiza|minimizar|restaura|restaurar)(?:\s+(?P<x>.+))?$",
)
def _window_state(m: re.Match[str], _: SystemIndex) -> Route:
    action = {"maxi": "maximize", "mini": "minimize", "rest": "restore"}[m.group("verb")[:4]]
    return _call("window_state", "window_layout", action=action, name=_window_name(m.group("x")))


@rule("window_side", r"^(?:pon|mueve|coloca|pasa)\s+(?P<x>.+?)\s+a la (?P<side>izquierda|derecha)$")
def _window_side(m: re.Match[str], _: SystemIndex) -> Route:
    action = "left" if m.group("side") == "izquierda" else "right"
    return _call("window_side", "window_layout", action=action, name=_window_name(m.group("x")))


@rule(
    "window_monitor",
    r"^(?:pon|mueve|pasa|lleva)\s+(?P<x>.+?)\s+al?\s+(?:otro|siguiente|segundo)\s+(?:monitor|pantalla)$",
)
def _window_monitor(m: re.Match[str], _: SystemIndex) -> Route:
    return _call(
        "window_monitor", "window_layout", action="next_monitor", name=_window_name(m.group("x"))
    )


@rule(
    "focus",
    r"^(?:cambia a|ve a|vete a|pasa a|muestrame|ensename|trae)\s+(?:la ventana de\s+)?(?P<x>.+)$",
)
def _focus(m: re.Match[str], index: SystemIndex) -> Route:
    return _call("focus", "focus_window", name=m.group("x"))


# --- abrir (lo último: es el patrón más general) ---

_IN_BROWSER = re.compile(r"\s+en (?:el )?(?:navegador|chrome|edge|firefox|internet)$")
_SETTINGS_PREFIX = re.compile(
    r"^(?:(?:la|las|los)\s+)?(?:configuracion|ajustes|opciones)(?:\s+(?:del|de la|de los|de las|de))?(?:\s+|$)"
)
_FOLDER_PREFIX = re.compile(r"^(?:la\s+)?carpeta(?:\s+(?:del|de))?\s+")
_INDEFINITE = ("un ", "una ", "otro ", "otra ", "nuevo ", "nueva ", "algo ", "alguna ")
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
