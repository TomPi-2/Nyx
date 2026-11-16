"""calendar: el calendario local de Nyx (tarea 8.02). Verde, con deshacer.

«Tengo dentista el jueves a las 5», «¿qué tengo mañana?», «¿qué tengo esta semana?», «mueve
la cita del dentista al viernes», «borra la reunión del lunes», «importa el calendario de
Descargas». Las citas con hora avisan 15 minutos antes (o lo que se diga) con las alarmas de
Nyx. Al leer un día salen también las tareas con fecha de ese día (8.01). Todo local
(`organizer/`); nada se borra del todo.
"""

from __future__ import annotations

import asyncio
import calendar as pycal
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Literal

from pydantic import Field

from nyx.organizer.calendar import (
    agenda,
    cancel_reminders,
    find_ics,
    import_ics,
    schedule_reminders,
)
from nyx.organizer.store import Event, OrganizerStore
from nyx.safety.undo import Undo
from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult
from nyx.tools.list_items import spoken_join

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
Weekday = Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DEFAULT_REMIND = 15
#: Los días de la semana como se dicen.
DAY_NAMES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


class CalendarParams(Params):
    action: Literal["add", "read", "move", "delete", "import"] = Field(
        description="add, read, move, delete, import"
    )
    title: str = Field(default="", max_length=200, description="La cita, sin la fecha")
    day: Literal["today", "tomorrow", "after_tomorrow"] | None = Field(
        default=None, description="Hoy, mañana o pasado"
    )
    weekday: Weekday | None = Field(default=None, description="El próximo lunes, martes…")
    date: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="Otro día (AAAA-MM-DD)"
    )
    month_day: int | None = Field(default=None, ge=1, le=31, description="«El día 20»")
    time: str | None = Field(
        default=None, pattern=r"^([01]?\d|2[0-3]):[0-5]\d$", description="Hora 24 h (HH:MM)"
    )
    minutes: int = Field(default=60, ge=5, le=24 * 60, description="Duración en minutos")
    remind: int | None = Field(
        default=None, ge=0, le=7 * 24 * 60, description="Avisar estos minutos antes"
    )
    repeat: Literal["none", "weekly", "monthly", "yearly"] = Field(
        default="none", description="Repetir cada semana, mes o año"
    )
    week: bool = Field(default=False, description="read: toda la semana")
    file: str = Field(default="", max_length=260, description="import: el .ics")


def resolve_day(params: CalendarParams, now: datetime) -> date | None:
    """El día que dice la petición, o None si no dice ninguno."""
    today = now.date()
    if params.date:
        return date.fromisoformat(params.date)
    if params.day is not None:
        return today + timedelta(days=("today", "tomorrow", "after_tomorrow").index(params.day))
    if params.weekday is not None:
        # «El jueves» dicho un jueves es el de la semana que viene.
        ahead = (WEEKDAYS.index(params.weekday) - today.weekday()) % 7 or 7
        return today + timedelta(days=ahead)
    if params.month_day is not None:
        year, month = today.year, today.month
        for _ in range(13):
            last = pycal.monthrange(year, month)[1]
            if params.month_day <= last and date(year, month, params.month_day) >= today:
                return date(year, month, params.month_day)
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return None


def _clock(text: str) -> time:
    hour, minute = (int(x) for x in text.split(":"))
    return time(hour, minute)


MONTHS = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def day_text(day: date, now: datetime) -> str:
    """«hoy», «mañana», «pasado mañana», «el jueves 20» o «el 3 de diciembre»."""
    days = (day - now.date()).days
    if 0 <= days <= 2:
        return ("hoy", "mañana", "pasado mañana")[days]
    if 0 < days < 7:
        return f"el {DAY_NAMES[day.weekday()]} {day.day}"
    return f"el {day.day} de {MONTHS[day.month - 1]}"


def when_label(start: datetime, now: datetime, *, all_day: bool) -> str:
    """«mañana a las 17:00», «el jueves 20 a las 10:00», «hoy» (todo el día)."""
    label = day_text(start.date(), now)
    return label if all_day else f"{label} a las {start:%H:%M}"


def event_when(event: Event, now: datetime) -> str:
    return when_label(datetime.fromtimestamp(event.start), now, all_day=event.all_day)


class CalendarTool(Tool[CalendarParams]):
    name = "calendar"
    description = (
        "Calendario: apuntar citas, ver un día o la semana, mover, borrar o importar .ics."
    )
    risk = Risk.GREEN
    game_policy = GamePolicy.ALLOWED
    category = Category.TIME
    params_model = CalendarParams
    observe = True

    async def run(self, params: CalendarParams, ctx: ToolContext) -> ToolResult:
        store = ctx.organizer
        if store is None:
            return ToolResult.fail("El calendario no está disponible")
        now = datetime.fromtimestamp(ctx.alarms.clock()) if ctx.alarms else datetime.now()
        if params.action == "read":
            return self._read(store, params, now)
        if params.action == "import":
            return await self._import(store, params, ctx, now)
        if not params.title.strip():
            return ToolResult.fail("¿Qué cita?")
        if params.action == "add":
            return self._add(store, params, ctx, now)
        found = store.find_events(params.title)
        if not found:
            return ToolResult.fail(f"No encuentro la cita «{params.title}»")
        if len(found) > 1:
            options = spoken_join([f"«{e.title}» {event_when(e, now)}" for e in found[:4]])
            return ToolResult.fail(f"Hay varias: {options}. ¿Cuál?")
        if params.action == "move":
            return self._move(store, found[0], params, ctx, now)
        return self._delete(store, found[0], ctx, now)

    # --- Apuntar, mover y borrar ------------------------------------------------------------------

    def _reschedule(self, store: OrganizerStore, ctx: ToolContext, now: datetime) -> None:
        if ctx.alarms is not None:
            schedule_reminders(store, ctx.alarms, now)

    def _add(
        self, store: OrganizerStore, params: CalendarParams, ctx: ToolContext, now: datetime
    ) -> ToolResult:
        day = resolve_day(params, now)
        if day is None:
            return ToolResult.fail("¿Qué día?")
        all_day = params.time is None
        start = datetime.combine(day, _clock(params.time) if params.time else time())
        if (start if not all_day else datetime.combine(day, time(23, 59))) <= now:
            return ToolResult.fail("Ese momento ya ha pasado")
        remind = (
            params.remind if params.remind is not None else (None if all_day else DEFAULT_REMIND)
        )
        event = store.add_event(
            params.title,
            start.timestamp(),
            minutes=24 * 60 if all_day else params.minutes,
            all_day=all_day,
            remind=remind,
            repeat=params.repeat,
        )
        self._reschedule(store, ctx, now)

        async def back() -> str:
            store.delete_event(event.id)
            cancel_reminders(store, ctx.alarms, event.id)
            return "Cita quitada"

        when = when_label(start, now, all_day=all_day)
        repeat = {"weekly": ", cada semana", "monthly": ", cada mes", "yearly": ", cada año"}.get(
            params.repeat, ""
        )
        return ToolResult(
            ok=True,
            message=f"Apuntado: {event.title}, {when}{repeat}.",
            display="Cita apuntada",
            secondary=f"{event.title} · {when}{repeat}",
            undo=Undo("Apuntar la cita", back),
        )

    def _move(
        self,
        store: OrganizerStore,
        event: Event,
        params: CalendarParams,
        ctx: ToolContext,
        now: datetime,
    ) -> ToolResult:
        old = datetime.fromtimestamp(event.start)
        day = resolve_day(params, now)
        if day is None and params.time is None:
            return ToolResult.fail("¿A qué día o a qué hora?")
        new_time = _clock(params.time) if params.time else old.time()
        start = datetime.combine(day or old.date(), new_time)
        all_day = event.all_day and params.time is None
        cancel_reminders(store, ctx.alarms, event.id)
        store.move_event(event.id, start.timestamp())
        self._reschedule(store, ctx, now)

        async def back() -> str:
            cancel_reminders(store, ctx.alarms, event.id)
            store.move_event(event.id, event.start)
            self._reschedule(store, ctx, now)
            return "Cita en su sitio otra vez"

        when = when_label(start, now, all_day=all_day)
        return ToolResult(
            ok=True,
            message=f"{event.title}: ahora {when}.",
            display="Cita movida",
            secondary=f"{event.title} · {when}",
            undo=Undo("Mover la cita", back),
        )

    def _delete(
        self, store: OrganizerStore, event: Event, ctx: ToolContext, now: datetime
    ) -> ToolResult:
        store.delete_event(event.id)
        cancel_reminders(store, ctx.alarms, event.id)

        async def back() -> str:
            store.delete_event(event.id, False)
            self._reschedule(store, ctx, now)
            return "Cita recuperada"

        return ToolResult(
            ok=True, message=f"Cita borrada: {event.title}.", undo=Undo("Borrar la cita", back)
        )

    # --- Ver ----------------------------------------------------------------------------------

    def _read(self, store: OrganizerStore, params: CalendarParams, now: datetime) -> ToolResult:
        day = resolve_day(params, now) or now.date()
        since = datetime.combine(day, time())
        until = since + timedelta(days=7 if params.week else 1)
        found = agenda(store, since, until)
        parts = []
        for o in found:
            when = (
                when_label(o.start, now, all_day=o.event.all_day)
                if params.week
                else ("todo el día" if o.event.all_day else f"a las {o.start:%H:%M}")
            )
            parts.append(f"{o.event.title} {when}")
        # Las tareas con fecha de ese día (o de la semana) también son «lo que tengo».
        for task in store.tasks(until=until.timestamp()):
            if task.due is not None and task.due >= since.timestamp():
                due = datetime.fromtimestamp(task.due)
                suffix = f" a las {due:%H:%M}" if task.alarm_id else ""
                parts.append(f"la tarea {task.text}{suffix}")
        span = "esta semana" if params.week else day_text(day, now)
        if not parts:
            return ToolResult(ok=True, message=f"No tienes nada {span}.", speak=True)
        head = span[0].upper() + span[1:]
        return ToolResult(
            ok=True,
            message=f"{head} tienes: {spoken_join(parts)}.",
            display=f"{head}: {len(parts)}",
            secondary=", ".join(parts)[:300],
            speak=True,
        )

    # --- Importar -------------------------------------------------------------------------------

    async def _import(
        self, store: OrganizerStore, params: CalendarParams, ctx: ToolContext, now: datetime
    ) -> ToolResult:
        from nyx.index.scanners.folders import known_folders

        folders = await asyncio.to_thread(known_folders)
        path = await asyncio.to_thread(find_ics, params.file, folders)
        if path is None:
            where = f"«{params.file}»" if params.file else "ningún calendario (.ics) en Descargas"
            return ToolResult.fail(f"No encuentro {where}")
        try:
            added, skipped = await asyncio.to_thread(import_ics, path, store, now)
        except (OSError, ValueError) as e:
            return ToolResult.fail(f"No he podido importar {path.name}: {e}")
        self._reschedule(store, ctx, now)

        async def back() -> str:
            for event_id in added:
                store.delete_event(event_id)
                cancel_reminders(store, ctx.alarms, event_id)
            return "Importación deshecha"

        extra = f" ({skipped} ya estaban o eran antiguas)" if skipped else ""
        return ToolResult(
            ok=True,
            message=f"He importado {len(added)} citas de {path.name}{extra}.",
            display=f"{len(added)} citas importadas",
            secondary=Path(path).name,
            undo=Undo("Importar el calendario", back) if added else None,
        )
