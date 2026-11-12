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
from nyx.stt.normalize import NUMBER_WORDS, WAKE_VARIANTS
from nyx.tools.app_catalog import profile_for
from nyx.tools.open_url import to_url
from nyx.winapi import windows


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
# «abre Spotify y maximízalo»: el verbo puede llevar pronombre pegado.
_SEVERAL_ACTIONS = re.compile(
    rf"\s(?:y|y luego|luego|despues|y despues)\s+(?:{_VERBS})(?:melo|mela|lo|la|los|las|le)?\b"
)


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
    clauses = _clauses(text)
    if len(clauses) > 1:
        return _route_several(clauses, index)
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


# Una orden nueva empieza por un verbo tras una coma o tras «y», «luego», «después».
_CLAUSE_VERBS = rf"(?:{_VERBS}|muestrame|ensename|quita|para|reanuda|ve a|vete a|cambia a)"
_CLAUSE_SPLIT = re.compile(
    rf"\s+(?:y luego|y despues|luego|despues|y)\s+(?=(?:{_CLAUSE_VERBS})"
    r"(?:melo|mela|lo|la|los|las|le)?\b)"
)
_STARTS_WITH_VERB = re.compile(rf"^(?:{_CLAUSE_VERBS})(?:melo|mela|lo|la|los|las|le)?\b")
# Lo que depende del paso anterior (escribir en la app recién abierta…): mejor el LLM, que
# añade las esperas.
_DEPENDENT = {"app_action", "send_hotkey"}


def _clauses(text: str) -> list[str]:
    """«Abre Discord, abre tus ajustes y pon música» → tres órdenes; [texto] si es una sola.

    Solo se parte cuando cada trozo empieza por un verbo, así «Chrome a la izquierda y
    Discord a la derecha» o «Dime, Nyx, ¿qué hora es?» siguen siendo una sola petición.
    """
    parts: list[str] = []
    for piece in re.split(r"[,;]", text):
        cleaned = _clean(piece)
        if cleaned:
            parts += [p for p in _CLAUSE_SPLIT.split(cleaned) if p]
    if len(parts) < 2 or not all(_STARTS_WITH_VERB.match(p) for p in parts):
        return [text]
    return parts


def _route_several(clauses: list[str], index: SystemIndex) -> Route | None:
    """Todas por reglas → un plan; si alguna no, el LLM se encarga de la frase entera."""
    calls: list[ToolCall] = []
    for clause in clauses:
        routed = route(clause, index)
        if not isinstance(routed, Route) or any(c.name in _DEPENDENT for c in routed.calls):
            return None
        calls += routed.calls
    return Route(calls, "several")


def _call(rule_name: str, tool: str, **arguments: object) -> Route:
    return Route([ToolCall(tool, {k: v for k, v in arguments.items() if v is not None})], rule_name)


# --- Ajustes de Nyx (lo primero: «muéstrame tus ajustes» no es cambiar de ventana, y
# «abre los ajustes de sonido» es la Configuración de Windows) ---

_NYX = "|".join(sorted(WAKE_VARIANTS))
_PANEL_WORDS = r"(?:ajustes|configuracion|opciones|preferencias)"


@rule(
    "nyx_settings",
    r"^(?:(?:abre|abrir|abreme|muestra|muestrame|ensena|ensename|ve a|ir a|entra en|llevame a)\s+)?"
    rf"(?:(?:(?:los|las|el|la)\s+)?{_PANEL_WORDS}\s+de\s+(?:{_NYX})\b|(?:tus|tu)\s+{_PANEL_WORDS}\b)"
    r"(?P<rest>.*)$",
)
def _nyx_settings(m: re.Match[str], _: SystemIndex) -> Route:
    rest = m.group("rest")
    section = None
    if re.search(r"partida|juego", rest):
        section = "partida"
    elif re.search(r"apariencia|aspecto|cristal|borde|tamano", rest):
        section = "apariencia"
    elif re.search(r"respuesta", rest):
        section = "respuestas"
    elif re.search(r"activacion|palabra|despertar|escucha", rest):
        section = "activacion"
    elif re.search(r"\bvoz\b|microfono|altavoz|auriculares|sonido", rest):
        section = "voz"
    elif re.search(r"cerebro|modelo|ollama|atajos aprendidos", rest):
        section = "cerebro"
    elif re.search(r"cache|escane", rest):
        section = "cache"
    elif re.search(r"privacidad|datos", rest):
        section = "privacidad"
    elif re.search(r"ayuda|registro", rest):
        section = "ayuda"
    elif re.search(r"general|ciudad|ubicacion|tiempo", rest):
        section = "general"
    return _call("nyx_settings", "open_nyx_settings", section=section)


# --- volumen (antes que «pon …» y «abre …») ---


# «sube el volumen de Spotify», «baja el sonido en Discord al 20», «sube el volumen al 50 en Spotify»
_APP_AT = r"(?:\s+(?:de|en|del)\s+(?P<app>[a-z0-9 ]+?))?"
_APP_AFTER = r"(?:\s+(?:de|en|del|para)\s+(?P<app2>[a-z0-9 ]+?))?"
_VOLUME_TAIL = (
    rf"(?P<much0>\s+mucho)?(?:\s+un poco)?\s+(?:el\s+)?(?:volumen|sonido){_APP_AT}(?:\s+(?:a|al|hasta(?:\s+el)?)\s+{_NUM})?"
    rf"{_APP_AFTER}(?P<much>\s+mucho)?(?:\s+un poco)?$"
)


def _volume(rule_name: str, m: re.Match[str], index: SystemIndex, step: int) -> Route | None:
    app_name = m.group("app") or m.group("app2")
    much = bool(m.group("much") or m.group("much0"))  # «sube mucho el volumen»
    app: str | None = None
    best = None
    if app_name:
        best = index.confident(index.resolve(app_name, {Kind.APP, Kind.GAME}))
        if best is None:
            return None  # que lo intente el LLM
        app = best.entry.name
    if m.group("n"):
        level = parse_number(m.group("n"))
        if level is None or level > 100:
            return None
        return _call(rule_name, "set_volume", level=level, app=app)
    action = "volume_up" if step > 0 else "volume_down"
    profile = profile_for(best.entry.process, app) if app_name and best else None
    if profile is not None and action in profile.actions:
        # Spotify tiene su propio volumen: se mueve su control (el del mezclador no se ve).
        return _call(rule_name, "app_action", app=app, action=action, times=2 if much else 1)
    return _call(rule_name, "set_volume", change=step * (2 if much else 1), app=app)


@rule("volume_up", rf"^(?:sube|subir|subeme|aumenta){_VOLUME_TAIL}")
def _volume_up(m: re.Match[str], index: SystemIndex) -> Route | None:
    return _volume("volume_up", m, index, 10)


@rule("volume_down", rf"^(?:baja|bajar|bajame|reduce){_VOLUME_TAIL}")
def _volume_down(m: re.Match[str], index: SystemIndex) -> Route | None:
    return _volume("volume_down", m, index, -10)


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
    r"^(?:pausa|pausar|para|parar|deten|pausa la|para la)(?:\s+(?:la\s+|el\s+)?(?:musica|cancion|video|reproduccion|(?P<app>spotify|youtube)))?"
    r"(?:\s+(?:de|en|del)\s+(?P<src>[a-z0-9 ]+))?$",
)
def _pause(m: re.Match[str], _: SystemIndex) -> Route:
    source = m.group("src") or m.group("app")
    return _call("media_pause", "media_control", action="pause", source=source)


@rule(
    "media_play",
    r"^(?:(?:reanuda|reanudar|continua|play|dale al play|dale a play|reproduce|quita la pausa)(?:\s+(?:la\s+|el\s+|a la\s+|al\s+)?(?:musica|cancion|video))?"
    r"|(?:pon|ponme|quiero)\s+(?:algo de\s+|un poco de\s+|la\s+)?musica)"
    r"(?:\s+(?:de|en|del)\s+(?P<src>[a-z0-9 ]+))?$",
)
def _play(m: re.Match[str], _: SystemIndex) -> Route:
    # «Pon música» (sin decir dónde) es poner música, no reanudar lo último que sonó.
    music = bool(re.match(r"(?:pon|ponme|quiero)\b", m.group(0))) and not m.group("src")
    return _call(
        "media_play", "media_control", action="play", source=m.group("src"), music=music or None
    )


@rule(
    "media_next",
    r"^(?:(?:pon\s+)?(?:la\s+)?siguiente|pasa(?:\s+de|\s+a)?(?:\s+la\s+siguiente)?|salta|skip)(?:\s+(?:cancion|tema|pista|video))?"
    r"(?:\s+(?:en|de|del)\s+[a-z0-9 ]+)?$",
)
def _next(m: re.Match[str], _: SystemIndex) -> Route:
    return _call("media_next", "media_control", action="next")


@rule(
    "media_previous",
    r"^(?:(?:pon\s+)?(?:la\s+)?anterior|(?:cancion|tema|pista) anterior|vuelve a la anterior)(?:\s+(?:cancion|tema|pista))?"
    r"(?:\s+(?:en|de|del)\s+[a-z0-9 ]+)?$",
)
def _previous(m: re.Match[str], _: SystemIndex) -> Route:
    return _call("media_previous", "media_control", action="previous")


# --- atajos de teclado (send_hotkey) ---

# Se mira si la app ya tiene ventana: si no, abrirla ya deja una pestaña nueva.
_find_windows = windows.find_windows


@rule(
    "new_tab",
    r"^(?:abre(?:me)?|crea(?:me)?|pon(?:me)?|haz(?:me)?)\s+(?:una\s+|otra\s+)?(?:nueva\s+(?:pestana|nota|ventana)|(?:pestana|nota)\s+nueva)"
    r"(?:\s+(?:dentro del|dentro de|en|del|de)\s+(?:el\s+|la\s+)?(?P<app>.+))?$",
)
def _new_tab(m: re.Match[str], index: SystemIndex) -> Route | None:
    if not m.group("app"):
        return _call("new_tab", "app_action", action="new_tab")
    best = index.confident(index.resolve(m.group("app"), {Kind.APP}))
    if best is None:
        return None
    name = best.entry.name
    if not _find_windows(name, best.entry.process):
        return _call("new_tab", "open_app", name=name)  # abrirla ya deja una nueva
    if profile_for(best.entry.process, name) is None:
        return _call("new_tab", "send_hotkey", keys="ctrl+t", app=name)
    return _call("new_tab", "app_action", app=name, action="new_tab")


def _app_named(m: re.Match[str], index: SystemIndex) -> tuple[bool, str | None]:
    """(válida, nombre de la app) para «… en Chrome»; sin app → la ventana activa."""
    raw = m.groupdict().get("app")
    if not raw:
        return True, None
    best = index.confident(index.resolve(raw, {Kind.APP}))
    return (best is not None, best.entry.name if best else None)


def _in_app(rule_name: str, action: str) -> Callable[[re.Match[str], SystemIndex], Route | None]:
    def handler(m: re.Match[str], index: SystemIndex) -> Route | None:
        ok, app = _app_named(m, index)
        return _call(rule_name, "app_action", action=action, app=app) if ok else None

    return handler


_IN = r"(?:\s+(?:en|de|del|dentro del?)\s+(?:el\s+|la\s+)?(?P<app>.+))?$"
rule("close_tab", r"^cierra(?:me)?\s+(?:la\s+|esta\s+)?pestana" + _IN)(
    _in_app("close_tab", "close_tab")
)
rule(
    "reopen_tab",
    r"^(?:reabre|recupera|vuelve a abrir)\s+(?:la\s+)?(?:ultima\s+)?pestana(?:\s+cerrada)?" + _IN,
)(_in_app("reopen_tab", "reopen_tab"))
rule("reload", r"^(?:recarga|refresca)(?:\s+(?:la\s+)?(?:pagina|web))?" + _IN)(
    _in_app("reload", "reload")
)
rule(
    "incognito",
    r"^abre(?:me)?\s+(?:una\s+)?(?:ventana\s+(?:de\s+)?)?(?:incognito|privada)" + _IN,
)(_in_app("incognito", "incognito"))
rule(
    "discord_mute",
    r"^(?:silencia|mutea|desmutea|desilencia|activa|desactiva|apaga|enciende)\s+(?:el\s+|mi\s+)?micro(?:fono)?(?:\s+(?:en|de)\s+discord)?$",
)(lambda m, index: _call("discord_mute", "app_action", app="Discord", action="toggle_mute"))
rule("discord_deafen", r"^ensordece(?:me)?(?:\s+(?:en|de)\s+discord)?$")(
    lambda m, index: _call("discord_deafen", "app_action", app="Discord", action="toggle_deafen")
)

rule(
    "save",
    r"^guarda(?:me)?(?:\s+(?:el\s+|la\s+|los\s+)?(?:documento|archivo|cambios|nota|texto))?" + _IN,
)(_in_app("save", "save"))


@rule(
    "fullscreen",
    r"^(?:(?:pon(?:me)?|haz|deja)\s+(?:el\s+|la\s+)?(?P<x>.+?)\s+(?:en\s+)?|)pantalla completa$",
)
def _fullscreen(m: re.Match[str], index: SystemIndex) -> Route | None:
    raw = m.group("x")
    if raw in (None, "esto", "la ventana", "esta ventana"):
        return _call("fullscreen", "app_action", action="fullscreen")
    best = index.confident(index.resolve(raw, {Kind.APP}))
    named = profile_for(best.entry.process if best else None, raw)
    app = best.entry.name if best else None
    if named is not None and "fullscreen" in named.actions:
        return _call("fullscreen", "app_action", action="fullscreen", app=app or raw)
    if app is None:
        return None
    return _call("fullscreen", "window_layout", action="maximize", name=app)


_SPOTIFY = r"(?:\s+(?:en|de)\s+spotify)?$"
rule(
    "shuffle",
    r"^(?:pon|activa|quita|desactiva)\s+(?:el\s+)?(?:modo\s+)?(?:aleatorio|shuffle)" + _SPOTIFY,
)(lambda m, index: _call("shuffle", "app_action", app="Spotify", action="shuffle"))
rule(
    "repeat",
    r"^(?:pon|activa|quita|desactiva)\s+(?:el\s+)?(?:modo\s+)?(?:repetir|bucle|repeticion)"
    + _SPOTIFY,
)(lambda m, index: _call("repeat", "app_action", app="Spotify", action="repeat"))
rule(
    "like",
    r"^(?:dale\s+(?:a\s+)?(?:un\s+)?me gusta|me gusta esta cancion|guarda esta cancion)"
    r"(?:\s+a\s+esta\s+cancion)?" + _SPOTIFY,
)(lambda m, index: _call("like", "app_action", app="Spotify", action="like"))


@rule(
    "two_windows",
    r"^(?:pon|mueve|coloca)\s+(?P<a>.+?)\s+a la (?P<s1>izquierda|derecha)\s+y\s+"
    r"(?:a\s+)?(?P<b>.+?)\s+a la (?P<s2>izquierda|derecha)$",
)
def _two_windows(m: re.Match[str], _: SystemIndex) -> Route:
    side = {"izquierda": "left", "derecha": "right"}
    return Route(
        [
            ToolCall("window_layout", {"action": side[m.group("s1")], "name": m.group("a")}),
            ToolCall("window_layout", {"action": side[m.group("s2")], "name": m.group("b")}),
        ],
        "two_windows",
    )


# --- lo que Nyx nunca hace (SPEC secciones 1 y 8) ---

_EMPTY_BIN = re.compile(r"\b(?:vacia|vaciar|limpia|limpiar|borra|borrar)\w*\s+(?:la\s+)?papelera\b")
_FOREVER = re.compile(
    r"\b(?:borra|elimina|borrar|eliminar)\w*\b.*\b(?:para siempre|permanentemente|definitivamente)\b"
)
# Nada de dinero (ACCIONES.md, reglas que no cambian): no puede depender del modelo, que a
# veces abría la tienda para «comprar unas zapatillas en Amazon».
_MONEY = re.compile(
    r"^(?:(?:puedes|podrias)\s+)?(?:compra\w*|paga|pagame|pagar|pagarme|"
    r"haz(?:me)? (?:un|el) pedido|pide(?:me)? (?:un|una|unos|unas)\b.*\b(?:en|a)\s+\w+|"
    r"transfiere|transferir|envia(?:le)? dinero|manda(?:le)? dinero)\b"
)
_IN_GAME = re.compile(
    r"\b(?:escribe|pulsa|teclea|dispara|apunta|juega|mueve|compra|vende|chat|chatea|"
    r"manda un mensaje)\b"
)


# Con una partida en marcha no hace falta nombrar el juego: «salta», «acelera», «dispara»…
# piden actuar dentro de él. «mueve» o «escribe» solos no cuentan («mueve Discord al otro
# monitor» se deja para después de la partida).
_PLAYING = re.compile(
    r"\b(?:salt[aeo]\w*|avanz\w*|aceler\w*|fren[aeo]\w*|gir[aeo]s?|girar|conduc\w*|"
    r"dispar\w*|apunt[aeo]s?|apuntar|recarg\w*|agach\w*|esquiv\w*|ataca\w*|defiend\w*|"
    r"constru\w*|juega|juegues|jugar por mi|tir[aeo]s?\s+(?:hacia|para)|"
    r"chatea\w*|manda un mensaje en el chat)\b"
    r"|\b(?:el coche|la pelota|el balon|el personaje|el muneco|mi jugador)\b"
)
IN_GAME_REFUSAL = ("Dentro de los juegos no toco nada", "puedo abrirlos, la música y el volumen")


def refusal(text: str, index: SystemIndex, *, playing: bool = False) -> tuple[str, str] | None:
    """(burbuja, línea secundaria) si es algo que Nyx no hace nunca; si no, None.

    `playing`: hay una partida en marcha (modo partida activo).
    """
    clean = _clean(text)
    if _EMPTY_BIN.search(clean) or _FOREVER.search(clean):
        return "Eso no lo hago", "borraría para siempre: lo que borro va a la papelera"
    if _MONEY.search(clean):
        return "Eso no lo hago", "no compro ni pago nada: puedo abrirte la web"
    if playing and _PLAYING.search(clean):
        return IN_GAME_REFUSAL
    if _IN_GAME.search(clean):
        games = {a for e in index.entries({Kind.GAME}) for a in (*e.aliases, normalize(e.name))}
        words = f" {clean} "
        if any(f" {alias} " in words for alias in games if len(alias) > 2):
            return IN_GAME_REFUSAL
    return None


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


# --- alarmas y temporizadores (bloque 3c; los recordatorios con texto van por el LLM) ---

_AMOUNT = rf"(?:(?P<n>{_N})\s+(?P<unit>segundos?|minutos?|horas?)(?P<half>\s+y\s+medi[oa])?|(?P<special>media hora|un cuarto de hora|tres cuartos de hora|hora y media))"
_UNIT_S = {"segundo": 1, "minuto": 60, "hora": 3600}
_SPECIAL_S = {
    "media hora": 1800,
    "un cuarto de hora": 900,
    "tres cuartos de hora": 2700,
    "hora y media": 5400,
}


def _seconds(m: re.Match[str]) -> int | None:
    if m.group("special"):
        return _SPECIAL_S[m.group("special")]
    n = parse_number(m.group("n"))
    if n is None:
        return None
    unit = _UNIT_S[m.group("unit").rstrip("s")]
    return n * unit + (unit // 2 if m.group("half") else 0)


@rule(
    "timer",
    rf"^(?:(?:(?:pon(?:me)?|crea|activa)\s+)?(?:un\s+)?temporizador\s+(?:de\s+)?"
    rf"|(?:avisame|despiertame|llamame|cuenta)\s+(?:en\s+)?"
    # «pon una alarma que suene en 10 segundos» es un temporizador (el LLM la ponía a las 00:10)
    rf"|(?:(?:pon(?:me)?|crea|activa)\s+)?(?:una\s+)?alarma\s+(?:que\s+suene\s+)?"
    rf"(?:en|dentro\s+de)\s+){_AMOUNT}$",
)
def _timer(m: re.Match[str], _: SystemIndex) -> Route | None:
    total = _seconds(m)
    if total is None or not 0 < total <= 24 * 3600:
        return None
    h, rest = divmod(total, 3600)
    mins, s = divmod(rest, 60)
    return _call("timer", "set_timer", hours=h or None, minutes=mins or None, seconds=s or None)


# «a las 7», «a las 7 30» (los dos puntos se quitan al normalizar), «a las 7 y media»,
# «a las 8 menos cuarto», «a las 5 de la tarde».
_CLOCK = rf"(?P<h>{_N})(?:\s+(?P<m>\d{{2}}))?(?:\s+y\s+(?P<frac>media|cuarto)|\s+(?P<minus>menos cuarto))?(?:\s+en punto)?(?:\s+(?:de la\s+|del\s+)?(?P<part>manana|tarde|noche|madrugada|mediodia))?"


def _clock_time(m: re.Match[str] | _Renamed) -> str | None:
    raw_h = m.group("h")
    h = parse_number(raw_h) if raw_h else None
    if h is None or h > 23:
        return None
    minute = int(m.group("m") or 0)
    if m.group("frac"):
        minute = 30 if m.group("frac") == "media" else 15
    if m.group("minus"):
        h, minute = (h - 1) % 24, 45
    part = m.group("part")
    if part in ("tarde", "noche") and h < 12:
        h += 12
    if part == "mediodia" and h < 5:  # «a la una del mediodía»
        h += 12
    if minute > 59:
        return None
    return f"{h:02d}:{minute:02d}"


_REPEAT_BODY = (
    r"(?:todos\s+los\s+)?(?:dias\s+)?laborables|"
    r"(?:de\s+)?lunes\s+a\s+viernes|"
    r"entre\s+semana|"
    r"(?:todos\s+)?los\s+fines\s+de\s+semana|"
    r"fines\s+de\s+semana|"
    r"todos\s+los\s+dias|"
    r"cada\s+dia|"
    r"a\s+diario|"
    r"diariamente"
)


def _parse_repeat(raw: str | None) -> str | None:
    if not raw:
        return None
    if "laborable" in raw or "lunes" in raw or "entre semana" in raw:
        return "weekdays"
    if "fin" in raw:
        return "weekends"
    return "daily"


@rule(
    "alarm",
    rf"^(?:(?:(?:pon(?:me)?|crea|activa)\s+)?(?:una\s+)?alarma\s+(?:para\s+)?|despiertame\s+)"
    rf"(?:(?P<rep1>{_REPEAT_BODY})\s+)?(?:(?P<day>manana|hoy)\s+)?(?:a\s+)?las?\s+{_CLOCK}"
    rf"(?:\s+(?P<rep2>{_REPEAT_BODY}))?$"
    rf"|^(?P<rep3>{_REPEAT_BODY})\s+(?:a\s+)?las?\s+{_CLOCK.replace('(?P<', '(?P<a_')}$",
)
def _alarm(m: re.Match[str], _: SystemIndex) -> Route | None:
    when = _clock_time(m) if m.group("h") is not None else _clock_time(_Renamed(m, "a_"))
    if when is None:
        return None
    tomorrow = m.group("day") == "manana"
    repeat = _parse_repeat(m.group("rep1") or m.group("rep2") or m.group("rep3"))
    return _call(
        "alarm", "set_alarm", time=when, day="tomorrow" if tomorrow else None, repeat=repeat
    )


_REMIND = r"(?:recuerdame|recordarme|avisame(?:\s+(?:para|de))?)"


@rule(
    "reminder",
    rf"^{_REMIND}\s+(?:(?P<rep1>{_REPEAT_BODY})\s+)?(?:(?P<day>manana|hoy)\s+)?(?:a\s+)?las?\s+{_CLOCK}\s+"
    rf"(?:(?P<rep2>{_REPEAT_BODY})\s+)?(?:que\s+|de\s+|para\s+)?(?P<label>.+)$"
    rf"|^{_REMIND}\s+(?:que\s+|de\s+)?(?P<label2>.+?)(?:\s+(?P<rep3>{_REPEAT_BODY}))?\s+"
    rf"(?:(?P<day2>manana|hoy)\s+)?a\s+las?\s+"
    + _CLOCK.replace("(?P<", "(?P<r_")
    + rf"(?:\s+(?P<rep4>{_REPEAT_BODY}))?$",
)
def _reminder(m: re.Match[str], _: SystemIndex) -> Route | None:
    """«Recuérdame a las 6 de la tarde llamar a mamá» y «recuérdame llamar a mamá a las 6».

    Con muchas herramientas, el 7B a veces escribía la orden como texto en vez de hacerla
    (tarea 6.03): lo frecuente y claro va por reglas."""
    first = m.group("label") is not None
    when = _clock_time(m) if first else _clock_time(_Renamed(m))
    if when is None:
        return None
    label = _original(m.group("label") if first else m.group("label2"))
    day = m.group("day") if first else m.group("day2")
    repeat = _parse_repeat(
        (m.group("rep1") or m.group("rep2")) if first else (m.group("rep3") or m.group("rep4"))
    )
    return _call(
        "reminder",
        "set_alarm",
        time=when,
        day="tomorrow" if day == "manana" else None,
        label=label,
        repeat=repeat,
    )


class _Renamed:
    """Los grupos del reloj con prefijo (`r_h`, `a_h`…) con los nombres de `_clock_time`."""

    def __init__(self, m: re.Match[str], prefix: str = "r_") -> None:
        self._m = m
        self._prefix = prefix

    def group(self, name: str) -> str | None:
        return self._m.group(f"{self._prefix}{name}")


def _original(fragment: str) -> str:
    """El trozo tal como lo dijo el usuario (con tildes y mayúsculas): «mama» → «mamá»."""
    words = _RAW.get().split()
    want = fragment.split()
    clean = [_clean(w) for w in words]
    for i in range(len(words) - len(want) + 1):
        if clean[i : i + len(want)] == want:
            return " ".join(words[i : i + len(want)]).strip(".,;:!?¡¿")
    return fragment


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
def _find(m: re.Match[str], index: SystemIndex) -> Route | None:
    folder = m.group("f")
    if (
        folder
        and index.confident(index.resolve(folder, {Kind.APP}))
        and not index.confident(index.resolve(folder, {Kind.FOLDER}))
    ):
        return None  # «busca un canal en Discord»: dentro de una app (LLM)
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
    if "portapapeles" in m.group("f"):
        return None
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
def _window_side(m: re.Match[str], _: SystemIndex) -> Route | None:
    if " y " in m.group("x"):
        return None  # dos ventanas: plan de varios pasos (LLM)
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


# --- alarmas: ver cuáles hay (6.03; antes el LLM decía «no tienes» sin mirar) ---


@rule(
    "alarms_list",
    r"^(?:que|cuales|cuantas) (?:alarmas|temporizadores|recordatorios) (?:tengo|hay)(?: puest[oa]s)?$"
    r"|^tengo (?:alguna |algun )?(?:alarmas?|temporizador(?:es)?|recordatorios?)(?: puest[oa]s?)?"
    r"(?: (?:para )?(?:hoy|manana|esta (?:tarde|noche)))?$"
    r"|^cuanto (?:le )?queda (?:al|a la|para la|para el) (?:temporizador|alarma|recordatorio)$",
)
def _alarms_list(_: re.Match[str], __: SystemIndex) -> Route:
    return _call("alarms_list", "list_alarms")


@rule(
    "alarms_cancel",
    r"^(?:cancela|quita|quitame|borra|elimina|anula)\s+(?:el|la|los|las|mi|mis)\s+"
    r"(?P<what>(?:temporizador|alarma|recordatorio)(?:es|s)?(?:\s+.+)?)$",
)
def _alarms_cancel(m: re.Match[str], __: SystemIndex) -> Route:
    """«Cancela el temporizador», «quita la alarma de las 7», «borra todas las alarmas»."""
    what = m.group("what")
    plural = re.match(r"(?:temporizador|alarma|recordatorio)(?:es|s)\b", what)
    which = "todas" if plural and not re.search(r"\bde\b", what) else what
    which = re.sub(r"^(?:alarma|recordatorio)\s+(?:de\s+)?(?:las\s+)?", "", which)
    return _call("alarms_cancel", "cancel_alarm", which=which)


# --- Nyx sobre sí misma (6.03; el 7B se lo inventaba: «puedo navegar por internet») ---


@rule(
    "self",
    r"^(?:(?:dime|explicame|cuentame)\s+)?(?:"
    r"que (?:cosas )?(?:puedes|sabes) hacer|que (?:cosas )?no (?:haces|puedes hacer|harias)"
    r"(?: nunca)?|quien eres|que eres|como funcionas"
    r"|(?:como (?:funciona|es) |que hace )?(?:tu|el) (?:modo partida|configuracion del modo "
    r"partida|configuracion para el modo partida|modo juego)"
    r")$",
)
def _self(m: re.Match[str], __: SystemIndex) -> Route:
    return _call("self", "nyx_info", topic=m.group(0))


# --- el tiempo (6.08) ---

_WHEN_WEATHER = (
    r"(?:ahora(?:\s+mismo)?|hoy|manana|pasado manana|"
    r"esta\s+(?:tarde|noche|semana)|este\s+fin\s+de\s+semana)"
)


@rule(
    "weather",
    r"^(?:(?:dime|mirame|consulta)\s+)?"
    r"(?:"
    rf"que\s+tiempo\s+(?:hace|hara|hay|va\s+a\s+hacer)|como\s+esta\s+el\s+(?:tiempo|dia|cielo)|"
    rf"que\s+tal\s+(?:el\s+tiempo|hace(?:\s+afuera|\s+fuera)?)|"
    rf"el\s+tiempo(?:\s+(?:de|para)\s+{_WHEN_WEATHER})?"
    r"|que\s+temperatura\s+(?:hace|hay|tenemos)|(?:a\s+)?cuantos\s+grados\s+(?:hace|hay|estamos)"
    r"|va\s+a\s+(?:llover|nevar)|llovera|nevara|esta\s+(?:lloviendo|nevando)|hay\s+tormenta"
    r"|hace\s+(?:frio|calor|viento|sol|buen\s+tiempo|mal\s+tiempo)"
    r"|(?:hace\s+falta|necesito|llevo|cojo)\s+(?:el\s+|un\s+)?(?:paraguas|abrigo|chaqueta)"
    r")"
    rf"(?:\s+(?:afuera|fuera|{_WHEN_WEATHER}))?"
    r"(?:\s+en\s+(?P<city>(?!la grafica|el procesador|la cpu|el pc|el ordenador)[a-z ]+?))?"
    rf"(?:\s+(?:afuera|fuera|{_WHEN_WEATHER}))?$",
)
def _weather(m: re.Match[str], __: SystemIndex) -> Route:
    raw = re.sub(rf"(?:^|\s+){_WHEN_WEATHER}$", "", m.group("city") or "").strip()
    city = _original(raw) if raw else None
    return _call("weather", "get_weather", city=city)


# --- estado del PC (6.09) ---

_PC_TAIL = r"(?:\s+(?:en\s+|de\s+|del\s+)?(?:el\s+|mi\s+|la\s+)?(?:pc|ordenador|equipo|portatil|sistema))?(?:\s+ahora(?:\s+mismo)?)?"


@rule(
    "system_info",
    r"^(?:(?:dime|mirame|consulta)\s+)?"
    r"(?:"
    r"(?P<top>(?:que|cual\s+es\s+el)\s+(?:(?P<top_p>proceso|programa|aplicacion|app)\s+(?:que\s+mas\s+)?)?"
    r"(?:(?:consume|usa|gasta|chupa)\s+mas(?:\s+(?:cpu|procesador|ram|memoria|recursos))?|"
    r"(?:cpu|procesador|ram|memoria|recursos)\s+(?:consume|usa|gasta|chupa)))"
    r"|(?P<battery>cuanta\s+bateria\s+(?:me\s+)?(?:queda|tengo|tiene|hay)|"
    r"(?:que\s+(?:porcentaje|nivel)\s+de\s+|a\s+cuanto\s+esta\s+la\s+|como\s+(?:va|esta)\s+la\s+)bateria|"
    r"esta\s+(?:enchufado|cargando))"
    r"|(?P<cpu>cuanta\s+cpu\s+(?:uso|estoy\s+usando|usa|consume|queda)|"
    r"(?:cual\s+es\s+el\s+|que\s+)uso\s+(?:de\s+(?:la\s+)?cpu|del\s+procesador)(?:\s+tengo|\s+hay)?|"
    r"(?:a\s+cuanto\s+(?:esta|va)|como\s+(?:esta|va))\s+(?:la\s+cpu|el\s+procesador)|"
    r"que\s+porcentaje\s+de\s+(?:cpu|procesador)\s+(?:uso|estoy\s+usando|hay))"
    r"|(?P<ram>cuanta\s+(?:memoria\s+)?ram\s+(?:uso|estoy\s+usando|tengo|me\s+queda|queda|hay(?:\s+libre)?|consume)|"
    r"cuanta\s+memoria\s+(?:uso|estoy\s+usando|me\s+queda|queda\s+libre|tengo\s+libre)|"
    r"(?:a\s+cuanto\s+(?:esta|va)|como\s+(?:esta|va)|cual\s+es\s+el\s+uso\s+de)\s+la\s+(?:memoria\s+)?ram)"
    r"|(?P<disk>cuanto\s+(?:espacio|disco|almacenamiento)(?:\s+libre)?\s+(?:me\s+)?(?:queda|tengo|hay)"
    r"(?:\s+libre)?(?:\s+en\s+(?:el\s+)?(?:disco(?:\s+duro)?|c))?|"
    r"espacio\s+libre(?:\s+en\s+(?:el\s+)?disco(?:\s+duro)?)?)"
    r")"
    rf"{_PC_TAIL}$",
)
def _system_info(m: re.Match[str], __: SystemIndex) -> Route | None:
    for kind in ("top", "battery", "cpu", "ram", "disk"):
        if m.group(kind):
            if (
                kind == "top"
                and not m.group("top_p")
                and not re.search(r"\b(?:cpu|procesador|ram|memoria|recursos)\b", m.group("top"))
            ):
                return None
            return _call("system_info", "system_info", what=kind)
    return None


# --- portapapeles y dictado (6.10) ---


@rule(
    "clipboard_read",
    r"^(?:(?:dime|mirame|ensename|lee(?:me)?)\s+)?(?:"
    r"que\s+(?:tengo|hay|he)\s+copiado(?:\s+en\s+el\s+portapapeles)?|"
    r"que\s+(?:tengo|hay)\s+en\s+el\s+portapapeles|"
    r"(?:el\s+)?portapapeles|"
    r"lo\s+(?:que\s+(?:tengo|hay|he)\s+)?copiado"
    r")$"
    r"|^(?:traduce(?:me)?(?:\s+al\s+[a-z]+)?|resume(?:me)?|corrige(?:me)?(?:\s+la\s+ortografia\s+de)?|explica(?:me)?)\s+"
    r"(?:lo\s+(?:que\s+(?:tengo|hay|he)\s+)?copiado|(?:lo\s+del\s+|el\s+)?portapapeles)(?:\s+al\s+[a-z]+)?$",
)
def _clipboard_read(_: re.Match[str], __: SystemIndex) -> Route:
    return _call("clipboard_read", "clipboard", action="read")


@rule(
    "clipboard_write",
    r"^(?:copia(?:me)?|guarda(?:me)?|pon(?:me)?)\s+(?:en\s+el\s+|al\s+)portapapeles\s+(?P<t1>.+)$"
    r"|^copia(?:me)?\s+(?P<t2>.+?)\s+(?:en\s+el\s+|al\s+)portapapeles$",
)
def _clipboard_write(m: re.Match[str], __: SystemIndex) -> Route:
    raw = (
        _raw_after(r"(?:en\s+el\s+|al\s+)portapapeles[:\s]+(.+)$")
        if m.group("t1")
        else _original(m.group("t2"))
    )
    return _call(
        "clipboard_write",
        "clipboard",
        action="write",
        text=raw or _original(m.group("t1") or m.group("t2")),
    )


@rule(
    "type_text",
    r"^(?:escribe|teclea|dicta)\s+(?!en\s+|un\s+|una\s+)(?P<text>.+)$",
)
def _type_text(m: re.Match[str], __: SystemIndex) -> Route:
    raw = _raw_after(r"(?:escribe|teclea|dicta)[:\s]+(.+)$")
    return _call("type_text", "type_text", text=raw or _original(m.group("text")))


# --- brillo, energía, Wi-Fi y Bluetooth (6.11) ---

_BRIGHTNESS_TAIL = (
    rf"(?P<much0>\s+mucho)?(?:\s+un poco)?\s+(?:el\s+)?brillo(?:\s+de\s+(?:la\s+)?pantalla)?"
    rf"(?:\s+(?:a|al|hasta(?:\s+el)?)\s+{_NUM}(?:\s*%|\s+por ciento)?)?"
    r"(?P<much>\s+mucho)?(?:\s+un poco)?$"
)


def _brightness(rule_name: str, m: re.Match[str], step: int) -> Route | None:
    if m.group("n"):
        level = parse_number(m.group("n"))
        if level is None or level > 100:
            return None
        return _call(rule_name, "set_brightness", level=level)
    much = bool(m.group("much") or m.group("much0"))
    return _call(rule_name, "set_brightness", change=step * (2 if much else 1))


@rule("brightness_up", rf"^(?:sube|subir|subeme|aumenta){_BRIGHTNESS_TAIL}")
def _brightness_up(m: re.Match[str], __: SystemIndex) -> Route | None:
    return _brightness("brightness_up", m, 20)


@rule("brightness_down", rf"^(?:baja|bajar|bajame|reduce){_BRIGHTNESS_TAIL}")
def _brightness_down(m: re.Match[str], __: SystemIndex) -> Route | None:
    return _brightness("brightness_down", m, -20)


@rule(
    "brightness_set",
    rf"^(?:(?:pon|deja|ajusta|cambia)\s+(?:el\s+)?)?brillo(?:\s+de\s+(?:la\s+)?pantalla)?\s+(?:a|al|en)?\s*(?:(?P<max>maximo|tope)|(?P<min>minimo)|{_NUM})(?:\s*%|\s+por ciento)?$",
)
def _brightness_set(m: re.Match[str], __: SystemIndex) -> Route | None:
    if m.group("max"):
        return _call("brightness_set", "set_brightness", level=100)
    if m.group("min"):
        return _call("brightness_set", "set_brightness", level=10)
    level = parse_number(m.group("n"))
    if level is None or level > 100:
        return None
    return _call("brightness_set", "set_brightness", level=level)


@rule(
    "radio_toggle",
    r"^(?:(?P<on>activa(?:r)?|enciende|encender|conecta(?:r)?|pon(?:er)?)|"
    r"(?P<off>desactiva(?:r)?|apaga(?:r)?|quita(?:r)?|desconecta(?:r)?)|"
    r"(?P<toggle>alterna(?:r)?|cambia(?:r)?))\s+(?:el\s+|la\s+)?(?P<kind>wi\s*fi|bluetooth)$",
)
def _radio_toggle(m: re.Match[str], __: SystemIndex) -> Route:
    tool = "toggle_wifi" if m.group("kind").startswith("wi") else "toggle_bluetooth"
    enabled = True if m.group("on") else (False if m.group("off") else None)
    return _call("radio_toggle", tool, enabled=enabled)


_PC_TARGET = r"(?:el\s+|mi\s+|la\s+)?(?:pc|ordenador|equipo|portatil|sistema|windows)"


@rule(
    "system_power",
    rf"^(?:(?P<lock>bloquea(?:r)?\s+(?:{_PC_TARGET}|(?:la\s+)?(?:pantalla|sesion)))"
    rf"|(?P<sleep>suspende(?:r)?\s+{_PC_TARGET}|pon(?:er)?\s+{_PC_TARGET}\s+(?:en\s+suspension|a\s+dormir))"
    rf"|(?P<restart>reinicia(?:r)?\s+{_PC_TARGET})"
    rf"|(?P<shutdown>apaga(?:r)?\s+{_PC_TARGET}))$",
)
def _system_power(m: re.Match[str], __: SystemIndex) -> Route | None:
    for action in ("lock", "sleep", "restart", "shutdown"):
        if m.group(action):
            return _call("system_power", "system_power", action=action)
    return None


# --- música actual, cronómetro y salida de audio (6.12) ---


@rule(
    "now_playing",
    r"^(?:(?:dime|sabes)\s+)?"
    r"(?:"
    r"que\s+(?:(?:cancion|tema|musica|pista|video)\s+)?(?:esta\s+sonando|suena)"
    r"(?:\s+ahora(?:\s+mismo)?)?(?:\s+en\s+[a-z0-9 ]+)?"
    r"|que\s+(?:cancion|tema|musica|pista)\s+es(?:\s+(?:esta|este))?"
    r"|como\s+se\s+llama\s+(?:esta\s+)?(?:cancion|tema|pista)(?:\s+que\s+(?:suena|esta\s+sonando))?"
    r"|(?:quien|de\s+quien)\s+(?:canta|es)\s+(?:esto|esta\s+(?:cancion|tema)|la\s+cancion(?:\s+que\s+suena)?)"
    r"|quien\s+canta"
    r")$",
)
def _now_playing(_: re.Match[str], __: SystemIndex) -> Route:
    return _call("now_playing", "now_playing")


_CRONO = r"(?:el\s+|un\s+|mi\s+)?(?:cronometro|crono)"


@rule(
    "stopwatch",
    rf"^(?P<start>(?:pon(?:me)?|empieza|inicia|arranca|activa|abre(?:me)?|dale\s+al?)\s+{_CRONO}|cronometro)$"
    rf"|^(?P<stop>(?:para|parame|deten|pausa|termina|corta)\s+{_CRONO})$"
    rf"|^(?P<status>(?:dime\s+)?(?:cuanto\s+(?:tiempo\s+)?lleva(?:\s+{_CRONO})?"
    rf"|(?:como\s+va|que\s+(?:tiempo\s+)?marca|estado\s+de(?:l)?)\s+(?:el\s+|mi\s+)?(?:cronometro|crono)))$",
)
def _stopwatch(m: re.Match[str], __: SystemIndex) -> Route | None:
    for action in ("start", "stop", "status"):
        if m.group(action):
            return _call("stopwatch", "stopwatch", action=action)
    return None


@rule(
    "audio_output",
    r"^(?:(?:cambia|cambiame|selecciona|elige|pon|ponme|saca|pasa|manda)\s+)?"
    r"(?:"
    r"(?:la\s+)?salida\s+(?:de\s+|del\s+)?(?:audio|sonido)"
    r"(?:\s+(?:a|al|en|por)\s+(?:los\s+|las\s+|el\s+|la\s+)?(?P<d1>.+))?"
    r"|(?:el\s+)?dispositivo\s+(?:de\s+)?(?:salida|reproduccion|audio)"
    r"(?:\s+(?:a|al|en|por)\s+(?:los\s+|las\s+|el\s+|la\s+)?(?P<d2>.+))?"
    r"|(?:el\s+)?(?:audio|sonido)\s+(?:a|en|por)\s+(?:los\s+|las\s+|el\s+|la\s+)?"
    r"(?P<d3>(?:auriculares|cascos|altavoces|bluetooth|hdmi|barra\s+de\s+sonido|monitor|tele(?:vision)?|tv|usb).*)"
    r")$",
)
def _audio_output(m: re.Match[str], __: SystemIndex) -> Route:
    raw = m.group("d1") or m.group("d2") or m.group("d3")
    device = _original(raw) if raw else None
    return _call("audio_output", "audio_output", device=device)


# --- lo pendiente para después de la partida ---


@rule(
    "pending",
    rf"^(?:dime\s+)?(?:(?:{_NYX})\s+)?(?:que|cuales?)\s+(?:cosas\s+)?(?:tienes|hay|te queda|tenemos)"
    r"\s+(?:de\s+|como\s+)?pendientes?(?:\s+(?:ahora|ahora mismo|para despues|al terminar))?$"
    r"|^que vas a hacer (?:despues|al terminar)(?: la partida)?$",
)
def _pending(_: re.Match[str], __: SystemIndex) -> Route:
    return _call("pending", "pending", action="list")


@rule(
    "pending_cancel",
    r"^(?:olvida|olvidate de|cancela|quita|no hagas)(?: nada de)? lo (?:pendiente|de despues)$",
)
def _pending_cancel(_: re.Match[str], __: SystemIndex) -> Route:
    return _call("pending_cancel", "pending", action="cancel")


@rule(
    "focus",
    r"^(?:cambia a|ve a|vete a|pasa a|muestrame|ensename|trae)\s+(?:la ventana de\s+)?(?P<x>.+)$",
)
def _focus(m: re.Match[str], index: SystemIndex) -> Route | None:
    # Solo si lo que se pide es una app o una ventana que existe: «muéstrame los FPS en el
    # Rocket League» no es «trae al frente la ventana "los fps…"» (ERRORES.md, 2026-11-11).
    name = m.group("x")
    if index.confident(index.resolve(name, {Kind.APP, Kind.GAME})) or _find_windows(name, None):
        return _call("focus", "focus_window", name=name)
    return None


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
