"""Pegar lo copiado y vaciar el texto de una nota (prueba del 2026-11-17).

«Pégalo en la nota», «pega lo que tengo copiado en Word», «escribe lo que tengo en el
portapapeles en la nota que tengo abierta» → Ctrl+V en esa app (antes se escribía la frase tal
cual o se leía en voz alta lo copiado). «Borra todo lo que hay en la nota» → Ctrl+A y Retroceso
en esa app (se deshace con Ctrl+Z); solo notas y documentos, nunca carpetas ni archivos.
"""

from __future__ import annotations

import re

from nyx.brain.router.comun import Route, _call, _original, rule
from nyx.index.service import SystemIndex

_NOTE = re.compile(
    r"^(?:la\s+)?nota(?:\s+(?:que\s+tengo\s+)?abierta)?$|^(?:el\s+)?bloc(?:\s+de\s+notas)?$"
)
_COPIED = (
    r"(?:lo\s+(?:que\s+(?:tengo|hay|he)\s+)?copiado|el\s+portapapeles|lo\s+del\s+portapapeles"
    r"|lo\s+que\s+(?:tengo|hay)\s+en\s+el\s+portapapeles|el\s+texto\s+copiado)"
)


def _app(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = re.sub(r"\s+(?:que\s+tengo\s+)?abiert[oa]$", "", raw.strip())
    if _NOTE.match(raw) or re.match(r"^(?:el\s+)?blog(?:\s+de\s+notas)?$", raw):
        return "Bloc de notas"
    return _original(re.sub(r"^(?:el|la)\s+", "", raw))


@rule(
    "paste",
    rf"^(?:pega(?:lo|la|me|melo)?|pegame)(?:\s+{_COPIED})?(?:\s+(?:en|dentro\s+de)\s+(?P<app>.+))?$"
    rf"|^(?:escribe|escribeme|pon|ponme|mete|meteme)\s+{_COPIED}"
    r"(?:\s+(?:en|dentro\s+de)\s+(?P<app2>.+))?$",
)
def _paste(m: re.Match[str], _: SystemIndex) -> Route:
    app = _app(m.group("app") or m.group("app2"))
    return _call("paste", "send_hotkey", keys="ctrl+v", app=app)


@rule(
    "clear_text",
    r"^(?:borra|borrame|elimina|quita|limpia|vacia)\s+(?:todo\s+)?(?:lo\s+que\s+(?:hay|pone|he\s+escrito)\s+)?"
    r"(?:(?:escrito\s+)?en|de)\s+(?P<app>(?:la\s+)?nota(?:\s+(?:que\s+tengo\s+)?abierta)?|"
    r"(?:el\s+)?bloc(?:\s+de\s+notas)?|(?:el\s+)?blog\s+de\s+notas)$"
    r"|^(?:vacia|limpia|borra)\s+(?:la\s+)?nota(?:\s+(?:que\s+tengo\s+)?abierta)?(?P<app2>)$",
)
def _clear_text(_: re.Match[str], __: SystemIndex) -> Route:
    app = "Bloc de notas"
    return Route(
        [
            *_call("clear_text", "send_hotkey", keys="ctrl+a", app=app).calls,
            *_call("clear_text", "send_hotkey", keys="backspace", app=app).calls,
        ],
        "clear_text",
    )
