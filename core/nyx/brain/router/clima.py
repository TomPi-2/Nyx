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
    r"esta\s+(?:tarde|noche|semana)|este\s+fin\s+de\s+semana)"
)


@rule(
    "weather",
    r"^(?:(?:dime|mirame|consulta)\s+)?"
    r"(?:"
    rf"que\s+tiempo\s+(?:hace|hara|hay|va\s+a\s+hacer|ha\s+hecho)|como\s+esta\s+el\s+(?:tiempo|dia|cielo)|"
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
