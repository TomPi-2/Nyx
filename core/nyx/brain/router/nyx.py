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
