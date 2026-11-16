"""Reglas de ocultar apps del todo y volver a enseñarlas (8.08).

«Oculta Discord del todo», «esconde WhatsApp de la barra», «quita Discord para que no se vea»,
«enséñalas», «enséñame las apps ocultas», «vuelve a mostrar Discord». «Oculta Discord» a
secas sigue siendo minimizar (ventanas.py).
"""

from __future__ import annotations

import re

from nyx.brain.router.comun import Route, _call, _original, rule
from nyx.index.service import SystemIndex


@rule(
    "hide_app",
    r"^(?:oculta(?:me)?|esconde(?:me)?|quita(?:me)?)\s+(?P<x>.+?)\s+"
    r"(?:del\s+todo|de\s+la\s+barra(?:\s+de\s+tareas)?|(?:para\s+)?que\s+no\s+se\s+vea(?:\s+nada)?)$",
)
def _hide_app(m: re.Match[str], _: SystemIndex) -> Route | None:
    app = re.sub(r"^(?:el|la|los|las)\s+", "", m.group("x"))
    if app in ("esto", "eso", "todo"):
        return None
    return _call("hide_app", "hide_apps", action="hide", app=_original(app))


@rule(
    "show_hidden",
    r"^(?:ensenal[oa]s?|muestral[oa]s?|"
    r"(?:ensename|muestrame|devuelveme|saca(?:me)?)\s+(?:lo\s+oculto|las\s+(?:apps|aplicaciones|ventanas)\s+ocultas)"
    r"|(?:vuelve\s+a\s+(?:mostrar(?:me)?|ensenar(?:me)?)|desoculta)\s+(?P<x>.+?))$",
)
def _show_hidden(m: re.Match[str], _: SystemIndex) -> Route | None:
    from nyx.winapi.hidden import HiddenWindows

    # «Enséñalo» tras «busca la factura» es el archivo: solo si hay algo oculto.
    if not HiddenWindows().hidden():
        return None
    app = m.group("x")
    if app and re.match(
        r"^(?:lo\s+oculto|las\s+(?:apps|aplicaciones|ventanas)(?:\s+ocultas)?)$", app
    ):
        app = None
    return _call("show_hidden", "hide_apps", action="show", app=_original(app) if app else None)
