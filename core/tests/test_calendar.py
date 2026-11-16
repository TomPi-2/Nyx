"""8.02: el calendario local (citas, repeticiones, avisos e importar un .ics)."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from nyx.alarms.scheduler import AlarmScheduler
from nyx.alarms.store import AlarmStore
from nyx.bus import EventBus
from nyx.organizer import calendar as cal
from nyx.organizer.store import Event, OrganizerStore
from nyx.tools.agenda import CalendarParams, CalendarTool, day_text, resolve_day
from nyx.tools.base import ToolContext
from nyx.tools.task import TaskParams, TaskTool

MONDAY = datetime(2026, 11, 16, 9, 0)  # lunes, 9:00
NOW = MONDAY.timestamp()


@pytest.fixture
def store(tmp_path: Path) -> OrganizerStore:
    return OrganizerStore(tmp_path / "organizer.db", clock=lambda: NOW)


@pytest.fixture
def octx(ctx: ToolContext, store: OrganizerStore, tmp_path: Path) -> ToolContext:
    ctx.organizer = store
    ctx.alarms = AlarmScheduler(AlarmStore(tmp_path / "a.db"), EventBus(), lambda: NOW)
    return ctx


def event(start: datetime, repeat: str = "none", *, all_day: bool = False) -> Event:
    return Event(1, "Algo", start.timestamp(), 60, all_day, 15, repeat)


def test_occurrences_repeat() -> None:
    week = cal.occurrences(
        event(datetime(2026, 1, 6, 18), "weekly"), MONDAY, MONDAY + timedelta(days=14)
    )
    assert week == [datetime(2026, 11, 17, 18), datetime(2026, 11, 24, 18)]
    # Cada mes el 31: noviembre no lo tiene, diciembre sí.
    month = cal.occurrences(
        event(datetime(2026, 10, 31, 10), "monthly"), MONDAY, datetime(2027, 1, 1)
    )
    assert month == [datetime(2026, 12, 31, 10)]
    year = cal.occurrences(
        event(datetime(2020, 11, 20), "yearly", all_day=True), MONDAY, datetime(2027, 1, 1)
    )
    assert year == [datetime(2026, 11, 20)]
    once = event(datetime(2026, 11, 16, 8, 30))  # empezó hace media hora y aún dura
    assert cal.occurrences(once, MONDAY, MONDAY + timedelta(days=1)) == [
        datetime(2026, 11, 16, 8, 30)
    ]


def test_resolve_day() -> None:
    def day(**kw: object) -> object:
        return resolve_day(CalendarParams(action="read", **kw), MONDAY)  # type: ignore[arg-type]

    assert day(day="after_tomorrow") == datetime(2026, 11, 18).date()
    assert day(weekday="thursday") == datetime(2026, 11, 19).date()
    assert day(weekday="monday") == datetime(2026, 11, 23).date()  # «el lunes» dicho un lunes
    assert day(month_day=10) == datetime(2026, 12, 10).date()  # el 10 ya pasó este mes
    assert day(month_day=31) == datetime(2026, 12, 31).date()  # noviembre no tiene 31
    assert day() is None
    assert day_text(datetime(2026, 11, 19).date(), MONDAY) == "el jueves 19"
    assert day_text(datetime(2026, 12, 3).date(), MONDAY) == "el 3 de diciembre"


async def test_add_read_move_delete_with_undo(octx: ToolContext) -> None:
    tool = CalendarTool()
    added = await tool.run(
        CalendarParams(action="add", title="Dentista", weekday="thursday", time="17:00"), octx
    )
    assert added.ok and added.message == "Apuntado: Dentista, el jueves 19 a las 17:00."
    assert octx.alarms is not None
    (alarm,) = octx.alarms.pending()
    assert alarm.label == "Dentista a las 17:00"
    assert alarm.due == datetime(2026, 11, 19, 16, 45).timestamp()  # 15 minutos antes

    await TaskTool().run(TaskParams(action="add", text="llamar al banco", date="2026-11-19"), octx)
    read = await tool.run(CalendarParams(action="read", weekday="thursday"), octx)
    assert read.message == "El jueves 19 tienes: Dentista a las 17:00 y la tarea llamar al banco."
    assert (await tool.run(CalendarParams(action="read"), octx)).message == "No tienes nada hoy."

    moved = await tool.run(CalendarParams(action="move", title="dentista", weekday="friday"), octx)
    assert moved.message == "Dentista: ahora el viernes 20 a las 17:00."
    (alarm,) = octx.alarms.pending()  # el aviso se mueve con la cita
    assert alarm.due == datetime(2026, 11, 20, 16, 45).timestamp()
    assert moved.undo is not None
    await moved.undo.action()
    (alarm,) = octx.alarms.pending()
    assert alarm.due == datetime(2026, 11, 19, 16, 45).timestamp()

    gone = await tool.run(CalendarParams(action="delete", title="Dentista"), octx)
    assert gone.ok and octx.alarms.pending() == []
    assert gone.undo is not None
    await gone.undo.action()  # vuelve, con su aviso
    assert len(octx.alarms.pending()) == 1


async def test_weekly_and_all_day(octx: ToolContext) -> None:
    tool = CalendarTool()
    await tool.run(
        CalendarParams(
            action="add", title="Clase de inglés", weekday="tuesday", time="18:00", repeat="weekly"
        ),
        octx,
    )
    await tool.run(CalendarParams(action="add", title="Boda de Luis", weekday="saturday"), octx)
    week = await tool.run(CalendarParams(action="read", week=True), octx)
    assert week.message == (
        "Esta semana tienes: Clase de inglés mañana a las 18:00 y Boda de Luis el sábado 21."
    )
    assert octx.alarms is not None
    # Cada semana: solo los avisos de los próximos 7 días (se renuevan cada hora).
    assert [a.label for a in octx.alarms.pending()] == ["Clase de inglés a las 18:00"]
    assert octx.organizer is not None
    assert cal.schedule_reminders(octx.organizer, octx.alarms, MONDAY + timedelta(days=7)) == 1


async def test_refuses_what_it_should(octx: ToolContext) -> None:
    tool = CalendarTool()
    past = await tool.run(CalendarParams(action="add", title="X", day="today", time="08:00"), octx)
    assert not past.ok and "pasado" in past.message
    no_day = await tool.run(CalendarParams(action="add", title="X", time="10:00"), octx)
    assert not no_day.ok and no_day.message == "¿Qué día?"
    missing = await tool.run(CalendarParams(action="delete", title="nada"), octx)
    assert not missing.ok
    for title in ("Reunión con Ana", "Reunión con Pablo"):
        await tool.run(CalendarParams(action="add", title=title, day="tomorrow"), octx)
    both = await tool.run(CalendarParams(action="delete", title="reunión"), octx)
    assert not both.ok and "¿Cuál?" in both.message


ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Prueba//ES
BEGIN:VEVENT
UID:a@x
SUMMARY:Reunión de equipo
DTSTART:20261118T100000
DTEND:20261118T110000
BEGIN:VALARM
TRIGGER:-PT30M
ACTION:DISPLAY
DESCRIPTION:Aviso
END:VALARM
END:VEVENT
BEGIN:VEVENT
UID:b@x
SUMMARY:Yoga
DTSTART:20250106T190000
DURATION:PT1H
RRULE:FREQ=WEEKLY
END:VEVENT
BEGIN:VEVENT
UID:c@x
SUMMARY:Algo de hace años
DTSTART:20200101T100000
END:VEVENT
BEGIN:VEVENT
UID:d@x
SUMMARY:Vacaciones
DTSTART;VALUE=DATE:20261224
DTEND;VALUE=DATE:20261226
END:VEVENT
END:VCALENDAR
"""


async def test_import_ics(
    octx: ToolContext, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    downloads = tmp_path / "Descargas"
    downloads.mkdir(exist_ok=True)
    (downloads / "trabajo.ics").write_text(ICS, encoding="utf-8")
    monkeypatch.setattr(
        "nyx.index.scanners.folders.known_folders", lambda: {"Descargas": downloads}
    )
    tool = CalendarTool()
    done = await tool.run(CalendarParams(action="import"), octx)
    assert done.ok and done.message == (
        "He importado 3 citas de trabajo.ics (1 ya estaban o eran antiguas)."
    )
    assert octx.organizer is not None
    by_title = {e.title: e for e in octx.organizer.events()}
    assert (
        by_title["Reunión de equipo"].remind == 30 and by_title["Reunión de equipo"].minutes == 60
    )
    assert by_title["Yoga"].repeat == "weekly" and by_title["Yoga"].remind is None
    assert by_title["Vacaciones"].all_day
    # Otra vez el mismo archivo: nada repetido.
    again = await tool.run(CalendarParams(action="import", file="trabajo"), octx)
    assert again.message.startswith("He importado 0 citas")
    assert done.undo is not None
    await done.undo.action()
    assert octx.organizer.events() == []
    nothing = await tool.run(CalendarParams(action="import", file="otro"), octx)
    assert not nothing.ok and "otro" in nothing.message
