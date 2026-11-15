"""Reglas sobre Nyx: sus ajustes, la ciudad, quién es y lo pendiente."""

from __future__ import annotations

import re

from nyx.brain.router.comun import (
    Route,
    _call,
    _original,
    rule,
)
from nyx.index.service import SystemIndex
from nyx.stt.normalize import WAKE_VARIANTS
from nyx.tools.nyx_control import COLORS

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


@rule(
    "city_set",
    r"^(?:(?:pon|configura|guarda|cambia|establece|fija)\s+(?:mi\s+|la\s+)?ciudad(?:\s+(?:a|en))?|mi\s+ciudad\s+es(?:\s+en)?)\s+(?P<city>.+)$",
)
def _city_set(m: re.Match[str], _: SystemIndex) -> Route:
    return _call("city_set", "nyx_control", setting="ciudad", value=_original(m.group("city")))


@rule(
    "city_live",
    # «vivo en Sevilla» (6.25); «vivo en un piso» o «vivo en casa de mis padres» no.
    r"^vivo\s+en\s+(?P<city>(?!(?:un|una|el|la|los|las|mi|mis|casa|el\s+centro)\b)[a-z ]+)$",
)
def _city_live(m: re.Match[str], _: SystemIndex) -> Route:
    return _call("city_live", "nyx_control", setting="ciudad", value=_original(m.group("city")))


_NYX_PART = {
    "voz": "voz",
    "color": "apariencia",
    "colores": "apariencia",
    "tamano": "apariencia",
    "letra": "apariencia",
    "aspecto": "apariencia",
    "palabra": "activacion",
    "palabra de activacion": "activacion",
    "tono": "respuestas",
}


@rule(
    "nyx_change",
    # «quiero cambiarte la voz», «quiero cambiar tu color» (6.25): lo de Nyx, en sus Ajustes.
    # «Quiero cambiar la voz del vídeo» no: tiene que ser «te» o «tu».
    r"^(?:quiero|me\s+gustaria|como\s+puedo)\s+(?:cambiarte\s+(?:la|el|los|las)|cambiar\s+tus?)\s+"
    r"(?P<what>voz|colores|color|tamano|letra|aspecto|palabra\s+de\s+activacion|palabra|tono)$",
)
def _nyx_change(m: re.Match[str], _: SystemIndex) -> Route:
    what = re.sub(r"\s+", " ", m.group("what"))
    # Su color y su tamaño: el panel junto a Nyx (9.11), no Ajustes.
    if (panel := _PANEL_OF.get(what)) is not None:
        return _call("nyx_change", "nyx_panel", panel=panel)
    return _call("nyx_change", "open_nyx_settings", section=_NYX_PART[what])


_PANEL_OF = {"color": "color", "colores": "color", "tamano": "tamaño"}


@rule(
    "nyx_panel",
    # «Cambia tu color», «cámbiate el color», «cámbiate de tamaño», «quiero elegir tu color»,
    # «cambia el color de los paneles», «quiero cambiar el color de tus paneles» (9.11). Sin un
    # color dicho: con color («ponte coral») lo hace nyx_color directamente.
    r"^(?:(?:quiero|me\s+gustaria|vamos\s+a)\s+)?"
    r"(?:cambia(?:r|me)?|cambiate|elige|elegir|escoge(?:r)?|personaliza(?:r)?)\s+"
    r"(?:(?:tu|el|de|tus)\s+)?"
    r"(?P<what>color|colores|tamano|"
    r"(?:color|colores|tono|tinte)\s+de\s+(?:los|tus|las)\s+(?:paneles|burbujas|ventanas))"
    r"(?:\s+de\s+(?:nyx|nix))?$",
)
def _nyx_panel(m: re.Match[str], _: SystemIndex) -> Route:
    what = m.group("what")
    panel = "paneles" if " de " in what else _PANEL_OF[what]
    return _call("nyx_panel", "nyx_panel", panel=panel)


@rule(
    "nyx_update",
    # «Actualízate», «instala la actualización», «actualiza Nyx», «ponte al día» (9.06).
    r"^(?:(?:puedes|quiero que te|venga)\s+)?(?:actualizate|actualizarte|actualiza(?:te)?\s+(?:a\s+)?(?:nyx|nix|la\s+version\s+nueva)"
    r"|instala(?:r)?\s+(?:la|tu)\s+(?:actualizacion|version\s+nueva)|ponte\s+al\s+dia)$",
)
def _nyx_update(_: re.Match[str], __: SystemIndex) -> Route:
    return _call("nyx_update", "nyx_update")


@rule(
    "nyx_size",
    # «Hazte más grande», «ponte un poco más pequeña», «vuélvete enorme» (9.11; antes iba al
    # modelo, y en el primer arranque fallaba).
    r"^(?:hazte|ponte|vuelvete|haste)\s+(?:un\s+poco\s+|algo\s+|mucho\s+|bastante\s+)?"
    r"(?:mas\s+)?(?P<v>grande|pequena|pequeno|pequenita|pequenito|chica|chico|enorme|diminuta)$",
)
def _nyx_size(m: re.Match[str], _: SystemIndex) -> Route:
    bigger = m.group("v") in ("grande", "enorme")
    value = "más grande" if bigger else "más pequeña"
    return _call("nyx_size", "nyx_control", setting="tamaño", value=value)


# Colores de Nyx (los de nyx_control), los compuestos primero: «azul cielo» antes que «azul».
_COLOR = "|".join(sorted(COLORS, key=len, reverse=True))


@rule(
    "nyx_color",
    # «ponte de color rosa», «cámbiate a color turquesa», «ponte azul cielo» (tanda 7).
    rf"^(?:ponte|cambiate|vuelvete|pintate)\s+(?:a\s+|de\s+|en\s+)?(?:color\s+)?(?P<c>{_COLOR})$",
)
def _nyx_color(m: re.Match[str], _: SystemIndex) -> Route:
    return _call("nyx_color", "nyx_control", setting="color", value=m.group("c"))


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


# --- Tepnyx (2026-11-14): quién ha creado a Nyx y qué son sus apps ---


@rule(
    "creator",
    # «¿Quién te ha creado?» contesta «Tepnyx» siempre (el 7B decía «Soy Nyx, tu asistente»).
    r"^(?:(?:y\s+)?(?:dime|sabes)\s+)?(?:"
    r"quien\s+te\s+(?:ha\s+)?(?:creado|hecho|programado|desarrollado|disenado|inventado|creo|hizo|"
    r"programo|desarrollo|diseno|invento)"
    r"|quien\s+(?:es|fue)\s+tu\s+(?:creador|creadora|desarrollador|desarrolladora|autor|padre|madre"
    r"|programador|programadora|dueno|duena)"
    r"|(?:que|cual\s+es\s+la)\s+empresa\s+(?:te\s+(?:ha\s+)?(?:hecho|creado|hizo|creo)|hay\s+detras"
    r"(?:\s+de\s+ti)?)|de\s+que\s+empresa\s+eres|quien\s+(?:esta|hay)\s+detras\s+de\s+ti"
    r"|quien\s+te\s+ha\s+traido\s+al\s+mundo"
    r")$",
)
def _creator(_: re.Match[str], __: SystemIndex) -> Route:
    return _call("creator", "nyx_info", topic="quien me ha creado")


_TEPNYX_THINGS = (
    r"tepnyx|tepnix|decider(?:\s+bot|\s+live)?|sorty|sorti|tirada|podio"
    r"|(?:la\s+)?ruleta\s+de\s+tepnyx"
)


@rule(
    "tepnyx_info",
    r"^(?:(?:dime|explicame|cuentame|sabes)\s+)?(?:"
    rf"que\s+es\s+(?:el\s+|la\s+)?(?P<a>{_TEPNYX_THINGS})"
    rf"|(?:hablame|que\s+sabes)\s+de\s+(?:el\s+|la\s+)?(?P<b>{_TEPNYX_THINGS})"
    r"|que\s+(?:apps|aplicaciones|productos|cosas)\s+(?:tiene|hace|ha\s+hecho)\s+(?P<c>tepnyx|tepnix)"
    rf"|(?:para\s+que\s+sirve|como\s+funciona)\s+(?:el\s+|la\s+)?(?P<d>{_TEPNYX_THINGS})"
    r")$",
)
def _tepnyx_info(m: re.Match[str], __: SystemIndex) -> Route:
    what = next(g for g in (m.group("a"), m.group("b"), m.group("c"), m.group("d")) if g)
    return _call("tepnyx_info", "nyx_info", topic=what)


# «¿Dónde cambio tu voz?»: el ajuste de Nyx, abierto en su sección (las pantallas de Nyx).
_WHERE_PART = {
    **_NYX_PART,
    "microfono": "voz",
    "altavoces": "voz",
    "velocidad": "voz",
    "monitor": "apariencia",
    "cristal": "apariencia",
    "paneles": "apariencia",
    "sensibilidad": "activacion",
    "atajos de teclado": "activacion",
    "atajos": "cerebro",
    "atajos aprendidos": "cerebro",
    "modelo": "cerebro",
    "cerebro": "cerebro",
    "ciudad": "general",
    "modo partida": "partida",
    "datos": "privacidad",
    "registro": "privacidad",
}


@rule(
    "nyx_where",
    r"^(?:donde|como)\s+(?:se\s+)?(?:cambio|cambia|pongo|pone|configuro|configura|elijo|elige"
    r"|ajusto|ajusta|quito|quita|activo|activa|desactivo|desactiva|veo|ve|borro|borra)\s+"
    r"(?:(?:tu|tus|el|la|los|las)\s+)?"
    rf"(?P<what>{'|'.join(sorted(_WHERE_PART, key=len, reverse=True))})"
    rf"(?P<own>\s+de\s+(?:{_NYX}))?$",
)
def _nyx_where(m: re.Match[str], __: SystemIndex) -> Route | None:
    text = m.group(0)
    # Tiene que ser de Nyx: «tu voz», «la voz de Nyx». «¿Dónde cambio el micrófono?» a secas
    # puede ser el de Windows: lo decide el modelo.
    if not m.group("own") and not re.search(r"\s(?:tu|tus)\s", f" {text} "):
        return None
    return _call("nyx_where", "open_nyx_settings", section=_WHERE_PART[m.group("what")])


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
    "nyx_said",
    # 6.25: ajustes de Nyx pedidos con rodeos.
    r"^(?P<shortcuts>donde\s+(?:veo|estan|puedo\s+ver|miro)\s+(?:los\s+)?atajos"
    r"(?:\s+que\s+has\s+aprendido)?)$"
    r"|^(?P<silent>cuando\s+te\s+escriba\s+no\s+me\s+(?:contestes|respondas)\s+(?:hablando|en\s+voz(?:\s+alta)?)"
    r"|no\s+me\s+hables\s+cuando\s+te\s+escriba)$"
    r"|^(?P<less>no\s+te\s+actives\s+tan\s+(?:facilmente|facil|rapido)|activate\s+menos"
    r"|no\s+saltes\s+tanto)$",
)
def _nyx_said(m: re.Match[str], _: SystemIndex) -> Route:
    if m.group("shortcuts"):
        return _call("nyx_said", "open_nyx_settings", section="cerebro")
    if m.group("silent"):
        return _call("nyx_said", "nyx_control", setting="voz al escribir", value="no")
    return _call("nyx_said", "nyx_control", setting="sensibilidad", value="menos")
