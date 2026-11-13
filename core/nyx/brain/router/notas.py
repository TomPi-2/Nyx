"""Reglas de notas (6.28): «apunta en una nota que mañana tengo dentista» → save_note.

Lo que se guarda va tal como lo dijo el usuario (con tildes y mayúsculas: `_original`). El
título son las primeras palabras. Solo con «nota» (o «apúntame que…», «toma nota de…»):
«guarda el documento» o «escribe en el bloc de notas» son otras cosas.
"""

from __future__ import annotations

import re

from nyx.brain.router.comun import Route, _call, _original, rule
from nyx.index.service import SystemIndex

TITLE_WORDS = 6


def _note(raw: str) -> Route | None:
    text = " ".join(_original(raw).split()).strip(" .,;:")
    if len(text) < 3:
        return None
    text = text[:1].upper() + text[1:]
    words = text.split()
    title = " ".join(words[:TITLE_WORDS]).rstrip(",;:")
    if len(words) > TITLE_WORDS:
        title += "…"
    if not text.endswith((".", "!", "?", "…")):
        text += "."
    return _call("note_save", "save_note", title=title, text=text)


@rule(
    "note_save",
    r"^(?:(?:apunta|apuntame|anota|anotame|guarda|guardame)\s+en\s+(?:una|la|mis)\s+notas?"
    r"(?:\s+que)?|(?:toma|tomame)\s+nota(?:\s+de)?(?:\s+que)?|"
    r"(?:crea|creame|haz|hazme)\s+una\s+nota\s+(?:que\s+(?:diga|ponga)|con|diciendo)(?:\s+que)?|"
    r"(?:apuntame|anotame)\s+que)\s+(?P<x>.+)$",
)
def _note_save(m: re.Match[str], _: SystemIndex) -> Route | None:
    return _note(m.group("x"))
