"""Reglas de listas y tareas (8.01): lo seguro sin pasar por el modelo.

«Añade leche y huevos a la lista de la compra», «¿qué hay en la lista de la compra?», «quita el
pan de la lista», «tacha los huevos», «vacía la lista de la compra», «¿qué listas tengo?»,
«apunta como tarea renovar el DNI», «¿qué tareas tengo hoy?». Lo que lleva fecha u hora
(«…mañana a las 10») va al modelo, que entiende mejor las fechas. «Apúntame que…» sigue siendo
una nota (`save_note`, notas.py).
"""

from __future__ import annotations

import re

from nyx.brain.router.comun import Route, _call, _original, rule
from nyx.index.service import SystemIndex

_LIST = r"(?P<l>(?:mi|la|una)\s+lista(?:\s+(?:de\s+la|de\s+las|de\s+los|del|de)\s+[a-z0-9 ]+)?)"
_ITEMS = r"(?P<x>.+?)"
# Una fecha u hora en lo que se apunta: mejor el modelo.
_WHEN = re.compile(
    r"\b(?:hoy|manana|pasado|lunes|martes|miercoles|jueves|viernes|sabado|domingo|a las?|"
    r"el dia|dentro de|esta (?:tarde|noche)|semana)\b"
)
# Listas de reproducción (Spotify…): no son de Nyx.
_MUSIC = re.compile(r"\b(?:cancion|canciones|reproduccion|playlist|spotify|musica|tema)\b")


def _music(m: re.Match[str]) -> bool:
    return bool(_MUSIC.search(m.group(0)))


@rule(
    "list_add",
    rf"^(?:anade|anademe|apunta|apuntame|anota|anotame|pon|ponme|mete|meteme|agrega)\s+"
    rf"{_ITEMS}\s+(?:a|en)\s+{_LIST}$",
)
def _list_add(m: re.Match[str], _: SystemIndex) -> Route | None:
    if _music(m):
        return None
    return _call(
        "list_add", "list_items", action="add", list=m.group("l"), items=_original(m.group("x"))
    )


@rule(
    "list_read",
    rf"^(?:que\s+(?:hay|tengo|pone|queda)\s+en|leeme|dime|ensename|muestrame|lee)\s+{_LIST}$",
)
def _list_read(m: re.Match[str], _: SystemIndex) -> Route | None:
    if _music(m):
        return None
    return _call("list_read", "list_items", action="read", list=m.group("l"))


@rule(
    "list_remove",
    rf"^(?:quita|quitame|borra|borrame|elimina|saca)\s+{_ITEMS}\s+de\s+{_LIST}$",
)
def _list_remove(m: re.Match[str], _: SystemIndex) -> Route | None:
    if _music(m):
        return None
    return _call(
        "list_remove",
        "list_items",
        action="remove",
        list=m.group("l"),
        items=_original(m.group("x")),
    )


@rule("list_done", rf"^tacha(?:me)?\s+{_ITEMS}(?:\s+de\s+{_LIST})?$")
def _list_done(m: re.Match[str], _: SystemIndex) -> Route | None:
    return _call(
        "list_done",
        "list_items",
        action="done",
        list=m.group("l") or None,
        items=_original(m.group("x")),
    )


@rule("list_clear", rf"^(?:vacia|vaciame|borra|limpia)\s+(?:toda\s+)?{_LIST}$")
def _list_clear(m: re.Match[str], _: SystemIndex) -> Route | None:
    if _music(m):
        return None
    return _call("list_clear", "list_items", action="clear", list=m.group("l"))


@rule("list_lists", r"^(?:que|cuales)\s+(?:listas\s+tengo|son\s+mis\s+listas)$")
def _list_lists(m: re.Match[str], _: SystemIndex) -> Route | None:
    return _call("list_lists", "list_items", action="lists")


@rule(
    "task_add",
    r"^(?:apunta|apuntame|anota|anotame|anade|anademe|crea|creame|pon|ponme)\s+"
    r"(?:como\s+tarea|una\s+tarea|la\s+tarea|tarea)(?:\s+de|\s+que|\s+para)?\s+(?P<x>.+)$",
)
def _task_add(m: re.Match[str], _: SystemIndex) -> Route | None:
    if _WHEN.search(m.group("x")):
        return None  # con fecha u hora: el modelo
    return _call("task_add", "task", action="add", text=_original(m.group("x")))


@rule(
    "task_read",
    r"^(?:que|cuantas)\s+tareas\s+(?:tengo|me\s+quedan|hay)(?:\s+(?:pendientes))?"
    r"(?:\s+(?P<d>hoy|para\s+hoy|manana|para\s+manana))?$",
)
def _task_read(m: re.Match[str], _: SystemIndex) -> Route | None:
    day = m.group("d") or ""
    when = "tomorrow" if "manana" in day else "today" if "hoy" in day else None
    return _call("task_read", "task", action="read", day=when)
