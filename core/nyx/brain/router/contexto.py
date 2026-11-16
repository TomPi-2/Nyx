"""Reglas de los recordatorios al abrir una app (8.03).

«Cuando abra Discord, recuérdame que le pase el enlace a Ana», «la próxima vez que entre en
Steam avísame de que hay rebajas», «recuérdame mirar el correo cuando abra Outlook». «Cuando
llegue a casa…» no (sin ubicación): va al modelo, que lo explica.
"""

from __future__ import annotations

import re

from nyx.brain.router.comun import Route, _call, _original, rule
from nyx.index.service import SystemIndex

_OPEN = r"(?:abra|abras|entre\s+en|inicie|arranque|me\s+meta\s+en|encienda)"
_WHEN = rf"(?:cuando|la\s+proxima\s+vez\s+que|en\s+cuanto)\s+{_OPEN}"
_DO = r"(?:recuerdame|recordarme|avisame|dime)(?:\s+(?:de\s+)?que|\s+de)?"


@rule(
    "app_reminder",
    rf"^{_WHEN}\s+(?:el\s+|la\s+)?(?P<app>.+?)\s+{_DO}\s+(?P<text>.+)$"
    rf"|^{_DO}\s+(?P<text2>.+?)\s+{_WHEN}\s+(?:el\s+|la\s+)?(?P<app2>.+)$",
)
def _app_reminder(m: re.Match[str], _: SystemIndex) -> Route | None:
    app = m.group("app") or m.group("app2")
    text = m.group("text") or m.group("text2")
    if re.search(r"\b(?:casa|trabajo|oficina|llegue|salga)\b", app):
        return None  # lugares: sin ubicación
    return _call(
        "app_reminder", "app_reminder", action="add", app=_original(app), text=_original(text)
    )
