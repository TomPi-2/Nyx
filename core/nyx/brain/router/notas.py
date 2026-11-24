"""Reglas de notas (6.28): «apunta en una nota que mañana tengo dentista» → save_note.

Lo que se guarda va tal como lo dijo el usuario (con tildes y mayúsculas: `_original`). El
título son las primeras palabras. Solo con «nota» (o «apúntame que…», «toma nota de…»):
«guarda el documento» o «escribe en el bloc de notas» son otras cosas.
"""

from __future__ import annotations

import re

from nyx.brain.router import comun
from nyx.brain.router.comun import Route, _call, _original, rule
from nyx.executor import ToolCall, with_waits
from nyx.index.model import Kind
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


# «Apunta en el bloc de notas la lista de la compra» (arnés, 2026-11-23: acababa abriendo los
# Ajustes de Nyx; y «apunta el blog de notas, pizza caprese» guardó una nota de Nyx con el texto
# cambiado). Es el Bloc de notas de Windows: se escribe allí; si no está abierto, se abre antes.
@rule(
    "note_in_notepad",
    # Sin «escribe»: «escribe en el bloc de notas X» ya lo resuelven las reglas de teclado.
    r"^(?:apunta|apuntame|anota|anotame|pon|ponme)\s+(?:en\s+)?(?:el\s+)?"
    r"(?:bloc|blog|block)\s+de\s+notas\s+(?:que\s+)?(?P<x>.+)$",
)
def _note_in_notepad(m: re.Match[str], index: SystemIndex) -> Route | None:
    text = " ".join(_original(m.group("x")).split()).strip(" ,;:")
    if len(text) < 2:
        return None
    best = index.confident(index.resolve("bloc de notas", {Kind.APP}))
    app = best.entry.name if best is not None else "Bloc de notas"
    if comun._find_windows(app, None):
        return _call("note_in_notepad", "type_text", app=app, text=text)
    calls = [ToolCall("open_app", {"name": app}), ToolCall("type_text", {"app": app, "text": text})]
    return Route(with_waits(calls), "note_in_notepad")
