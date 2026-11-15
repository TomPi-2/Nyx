"""8.01: listas y tareas por el router (sin el modelo)."""

from __future__ import annotations

from typing import Any

import pytest

from nyx.brain.router import Route, route
from nyx.index.service import SystemIndex


@pytest.mark.parametrize(
    ("text", "rule", "args"),
    [
        (
            "Añade leche, huevos y pan a la lista de la compra",
            "list_add",
            {"action": "add", "list": "la lista de la compra", "items": "leche, huevos y pan"},
        ),
        (
            "apunta tomates en mi lista",
            "list_add",
            {"action": "add", "list": "mi lista", "items": "tomates"},
        ),
        (
            "¿qué hay en la lista de la compra?",
            "list_read",
            {"action": "read", "list": "la lista de la compra"},
        ),
        (
            "léeme mi lista de pendientes",
            "list_read",
            {"action": "read", "list": "mi lista de pendientes"},
        ),
        (
            "vacía la lista de la compra",
            "list_clear",
            {"action": "clear", "list": "la lista de la compra"},
        ),
        (
            "borra la lista de la compra",
            "list_clear",
            {"action": "clear", "list": "la lista de la compra"},
        ),
        (
            "quita el pan de la lista de la compra",
            "list_remove",
            {"action": "remove", "list": "la lista de la compra", "items": "el pan"},
        ),
        ("tacha los huevos", "list_done", {"action": "done", "items": "los huevos"}),
        ("¿qué listas tengo?", "list_lists", {"action": "lists"}),
        (
            "apunta como tarea renovar el DNI",
            "task_add",
            {"action": "add", "text": "renovar el DNI"},
        ),
        (
            "añade una tarea: llamar al fontanero",
            "task_add",
            {"action": "add", "text": "llamar al fontanero"},
        ),
        ("¿qué tareas tengo hoy?", "task_read", {"action": "read", "day": "today"}),
        ("¿qué tareas tengo pendientes?", "task_read", {"action": "read"}),
    ],
)
def test_lists_and_tasks(index: SystemIndex, text: str, rule: str, args: dict[str, Any]) -> None:
    routed = route(text, index)
    assert isinstance(routed, Route) and routed.rule == rule
    (call,) = routed.calls
    assert call.arguments == args


@pytest.mark.parametrize(
    "text",
    [
        "añade esta canción a mi lista de reproducción",  # Spotify, no Nyx
        "apunta como tarea llamar al banco mañana a las 10",  # con fecha: el modelo
        "apúntame que mañana tengo dentista",  # una nota (save_note)
        "borra las capturas del escritorio",
        "pon música",
    ],
)
def test_not_lists(index: SystemIndex, text: str) -> None:
    routed = route(text, index)
    assert not (isinstance(routed, Route) and routed.rule.startswith(("list_", "task_")))
