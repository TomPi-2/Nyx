"""Reglas de los modos (8.10): «modo trabajo», «activa el modo noche», «pon el modo
privacidad», «sal del modo trabajo», «quita el modo», «¿en qué modo estás?»."""

from __future__ import annotations

import re

from nyx.brain.router.comun import Route, _call, rule
from nyx.index.service import SystemIndex


@rule(
    "mode",
    r"^(?:(?:activa(?:me)?|pon(?:me)?|entra\s+en|pasa\s+a|cambia\s+a|empieza)\s+(?:el\s+)?)?"
    r"modo\s+(?P<m>[a-z]+(?:\s+[a-z]+)?)$"
    r"|^(?P<exit>(?:sal|salte|salir)\s+del\s+modo(?:\s+[a-z]+)?|(?:quita|desactiva|apaga)\s+el\s+modo"
    r"(?:\s+[a-z]+)?|modo\s+normal|vuelve\s+a\s+lo\s+normal)$"
    r"|^(?P<status>en\s+que\s+modo\s+(?:estas|estamos)|que\s+modo\s+(?:tienes|hay)(?:\s+puesto)?)$",
)
def _mode(m: re.Match[str], _: SystemIndex) -> Route | None:
    if m.group("status"):
        return _call("mode", "mode", action="status")
    if m.group("exit"):
        return _call("mode", "mode", action="exit")
    name = m.group("m")
    # «modo avión», «modo oscuro», «modo partida»: no son modos de Nyx (Windows o el juego).
    # «modo dictado» es el dictado (dictado.py), no un modo.
    if name in (
        "avion", "oscuro", "claro", "partida", "juego", "desarrollador", "incognito", "dictado"
    ):  # fmt: skip
        return None
    return _call("mode", "mode", action="enter", mode=name)
