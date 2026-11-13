"""Regla del tiempo."""

from __future__ import annotations

import re

from nyx.brain.router.comun import (
    Route,
    _call,
    _original,
    rule,
)
from nyx.index.service import SystemIndex

# --- el tiempo (6.08) ---

_WHEN_WEATHER = (
    r"(?:ahora(?:\s+mismo)?|hoy|manana|pasado manana|"
    r"esta\s+(?:tarde|noche|semana)|este\s+fin\s+de\s+semana|este\s+finde)"
)


# Tras «en» no siempre va una ciudad: «hace frío en casa» no es el tiempo de un pueblo
# llamado Casa (6.25).
_NOT_A_CITY = (
    r"(?!la grafica|el procesador|la cpu|el pc|el ordenador|casa\b|mi casa|la oficina|el trabajo"
    r"|clase\b|la clase|la calle|el cuarto|la habitacion|el salon)"
)


@rule(
    "weather",
    r"^(?:tengo\s+(?:frio|calor)\s+)?(?:(?:dime|mirame|consulta)\s+)?"
    r"(?:"
    rf"que\s+tiempo\s+(?:hace|hara|hay|va\s+a\s+hacer|ha\s+hecho)|como\s+esta\s+el\s+(?:tiempo|dia|cielo)|"
    rf"que\s+tal\s+(?:el\s+tiempo|hace(?:\s+afuera|\s+fuera)?)|"
    rf"el\s+tiempo(?:\s+(?:de|para)\s+{_WHEN_WEATHER})?"
    r"|que\s+temperatura\s+(?:hace|hay|tenemos)"
    r"|(?:a\s+)?cuantos\s+grados\s+(?:hace|hay|estamos|va\s+a\s+hacer|hara)"
    # 6.25: «¿qué tal día va a hacer?», «¿hará bueno?», «¿está nublado?»
    r"|(?:que\s+tal|como)\s+(?:dia|tiempo)\s+(?:va\s+a\s+hacer|hara|hace)"
    r"|(?:hara|va\s+a\s+hacer)\s+(?:bueno|malo|frio|calor|sol|viento|buen\s+tiempo|mal\s+tiempo)"
    r"|(?:esta|va\s+a\s+estar)\s+(?:nublado|despejado)"
    r"|va\s+a\s+(?:llover|nevar)|llovera|nevara|esta\s+(?:lloviendo|nevando)|hay\s+tormenta"
    r"|hace\s+(?:frio|calor|viento|sol|buen\s+tiempo|mal\s+tiempo)"
    r"|(?:tengo\s+que|hace\s+falta|necesito|me\s+llevo|llevo|cojo)\s+"
    r"(?:(?:coger|llevar(?:me)?|sacar)\s+)?(?:el\s+|la\s+|un\s+|una\s+)?"
    r"(?:paraguas|abrigo|chaqueta|chubasquero|sudadera|rebeca)(?:\s+para\s+salir)?"
    r")"
    rf"(?:\s+(?:afuera|fuera|{_WHEN_WEATHER}))?"
    rf"(?:\s+en\s+(?P<city>{_NOT_A_CITY}[a-z ]+?))?"
    rf"(?:\s+(?:afuera|fuera|{_WHEN_WEATHER}))?$",
)
def _weather(m: re.Match[str], __: SystemIndex) -> Route:
    raw = re.sub(rf"(?:^|\s+){_WHEN_WEATHER}$", "", m.group("city") or "").strip()
    city = _original(raw) if raw else None
    return _call("weather", "get_weather", city=city)
