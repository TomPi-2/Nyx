"""Reglas del dictado (8.04): «escribe lo que te diga», «empieza el dictado en Word»,
«voy a dictar», «termina el dictado». «Escribe hola en el Bloc de notas» (con el texto) sigue
siendo `type_text`.
"""

from __future__ import annotations

import re

from nyx.brain.router.comun import Route, _call, _original, rule
from nyx.index.service import SystemIndex

_IN = r"(?:\s+en\s+(?:el\s+|la\s+)?(?P<app>.+))?"


@rule(
    "dictation",
    r"^(?:(?:ahora\s+)?(?:escribe|escribeme|apunta|transcribe|redacta|redactame)"
    r"(?:\s+(?:tu|todo))?\s+lo\s+que\s+(?:yo\s+)?(?:te\s+)?"
    r"(?:diga|vaya\s+diciendo|dicte|voy\s+a\s+decir|vaya\s+a\s+decir)"
    r"|(?:empieza|activa|inicia|pon|comienza|abre)\s+(?:el\s+|un\s+)?(?:modo\s+)?dictado"
    # «Te voy a dictar y tienes que escribir lo que te diga» (2026-11-17)
    r"|(?:te\s+)?(?:voy\s+a|quiero)\s+dictar(?:te)?(?:\s+algo)?(?:\s+y\s+.+)?"
    rf"|dictado){_IN}$"
    r"|^(?P<stop>(?:termina|para|desactiva|acaba|cierra|quita)\s+(?:el\s+)?dictado)$",
)
def _dictation(m: re.Match[str], _: SystemIndex) -> Route:
    if m.group("stop"):
        return _call("dictation", "dictation", action="stop")
    app = m.group("app")
    return _call("dictation", "dictation", action="start", app=_original(app) if app else None)
