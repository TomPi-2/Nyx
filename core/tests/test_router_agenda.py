"""8.02: el calendario por el router (sin el modelo)."""

from __future__ import annotations

from typing import Any

import pytest

from nyx.brain.router import Route, route
from nyx.index.service import SystemIndex


@pytest.mark.parametrize(
    ("text", "rule", "args"),
    [
        ("¿Qué tengo mañana?", "agenda_read", {"action": "read", "day": "tomorrow"}),
        ("¿Qué tengo esta semana?", "agenda_read", {"action": "read", "week": True}),
        ("¿Tengo algo el jueves?", "agenda_read", {"action": "read", "weekday": "thursday"}),
        ("Enséñame mi agenda de hoy", "agenda_read", {"action": "read", "day": "today"}),
        ("¿Qué tengo en el calendario?", "agenda_read", {"action": "read"}),
        (
            "Tengo dentista el jueves a las 5",
            "agenda_add",
            {"action": "add", "title": "Dentista", "weekday": "thursday", "time": "17:00"},
        ),
        (
            "Tengo una reunión con Ana mañana a las 10",
            "agenda_add",
            {"action": "add", "title": "Reunión con Ana", "day": "tomorrow", "time": "10:00"},
        ),
        (
            "Apunta una cita con el dentista el jueves a las 5 y media",
            "agenda_add",
            {
                "action": "add",
                "title": "Cita con el dentista",
                "weekday": "thursday",
                "time": "17:30",
            },
        ),
        (
            "Tengo clase de inglés todos los martes a las 6",
            "agenda_add",
            {
                "action": "add",
                "title": "Clase de inglés",
                "weekday": "tuesday",
                "time": "18:00",
                "repeat": "weekly",
            },
        ),
        (
            "Tengo médico el día 20 a las 9 de la mañana",
            "agenda_add",
            {"action": "add", "title": "Médico", "month_day": 20, "time": "09:00"},
        ),
        (
            "Apunta en el calendario la boda de Luis el sábado",
            "agenda_add",
            {"action": "add", "title": "La boda de Luis", "weekday": "saturday"},
        ),
        (
            "Apunta una reunión para el lunes a las 10",
            "agenda_add",
            {"action": "add", "title": "Reunión", "weekday": "monday", "time": "10:00"},
        ),
        (
            "Mueve la cita del dentista al viernes",
            "agenda_move",
            {"action": "move", "title": "dentista", "weekday": "friday"},
        ),
        (
            "Pasa la reunión con Ana a las 11",
            "agenda_move",
            {"action": "move", "title": "Ana", "time": "11:00"},
        ),
        (
            "Cancela la cita del dentista",
            "agenda_delete",
            {"action": "delete", "title": "dentista"},
        ),
        ("Importa el calendario de Descargas", "agenda_import", {"action": "import"}),
    ],
)
def test_agenda(index: SystemIndex, text: str, rule: str, args: dict[str, Any]) -> None:
    routed = route(text, index)
    assert isinstance(routed, Route) and routed.rule == rule
    (call,) = routed.calls
    assert call.arguments == args


@pytest.mark.parametrize(
    "text",
    [
        "tengo que levantarme a las 7",  # alarma
        "tengo que llamar a mamá mañana",  # al modelo (o tarea)
        "cambia el volumen a 30",
        "pasa la canción",
        "apunta leche en la lista de la compra",
        "cancela la alarma de las 7",
        "pon una alarma mañana a las 7",
        "¿qué tareas tengo hoy?",
    ],
)
def test_not_agenda(index: SystemIndex, text: str) -> None:
    routed = route(text, index)
    assert not (isinstance(routed, Route) and routed.rule.startswith("agenda_"))
