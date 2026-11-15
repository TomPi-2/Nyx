"""task: tareas con fecha opcional (tarea 8.01). Verde, con deshacer.

«Apunta como tarea llamar al banco mañana a las 10», «¿qué tareas tengo hoy?», «ya he llamado
al banco» (hecha), «borra la tarea del banco». Con hora, avisa como un recordatorio (alarmas de
Nyx); sin hora, se queda para ese día. Todo local (`organizer/store.py`); nada se borra del todo.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal

from pydantic import Field

from nyx.alarms.spoken import day_label
from nyx.organizer.store import OrganizerStore, Task
from nyx.safety.undo import Undo
from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult
from nyx.tools.list_items import spoken_join

#: Sin hora, una tarea de un día vence al final de ese día.
END_OF_DAY = (23, 59)


class TaskParams(Params):
    action: Literal["add", "done", "read", "delete"] = Field(description="add, done, read, delete")
    text: str = Field(default="", max_length=200, description="La tarea, sin la fecha")
    day: Literal["today", "tomorrow"] | None = Field(default=None, description="Hoy o mañana")
    date: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="Otro día (AAAA-MM-DD)"
    )
    time: str | None = Field(
        default=None, pattern=r"^([01]?\d|2[0-3]):[0-5]\d$", description="Hora 24 h (HH:MM)"
    )


class TaskTool(Tool[TaskParams]):
    name = "task"
    description = "Tareas: apuntar (con día y hora opcionales), marcar hecha, ver o borrar."
    risk = Risk.GREEN
    game_policy = GamePolicy.ALLOWED
    category = Category.TIME
    params_model = TaskParams
    observe = True

    async def run(self, params: TaskParams, ctx: ToolContext) -> ToolResult:
        store = ctx.organizer
        if store is None:
            return ToolResult.fail("Las tareas no están disponibles")
        now = datetime.fromtimestamp(ctx.alarms.clock()) if ctx.alarms else datetime.now()
        if params.action == "read":
            return self._read(store, params, now)
        if not params.text.strip():
            return ToolResult.fail("¿Qué tarea?")
        if params.action == "add":
            return self._add(store, params, ctx, now)
        found = store.find_tasks(params.text)
        if not found:
            return ToolResult.fail(f"No encuentro la tarea «{params.text}»")
        if len(found) > 1:
            options = spoken_join([f"«{t.text}»" for t in found[:5]])
            return ToolResult.fail(f"Hay varias: {options}. ¿Cuál?")
        return self._close(store, found[0], ctx, done=params.action == "done")

    @staticmethod
    def _day(params: TaskParams, now: datetime) -> date | None:
        if params.date:
            return date.fromisoformat(params.date)
        if params.day == "tomorrow":
            return (now + timedelta(days=1)).date()
        if params.day == "today" or params.time:
            return now.date()
        return None

    def _add(
        self, store: OrganizerStore, params: TaskParams, ctx: ToolContext, now: datetime
    ) -> ToolResult:
        day = self._day(params, now)
        due: datetime | None = None
        alarm_id: str | None = None
        if day is not None:
            hour, minute = (int(x) for x in params.time.split(":")) if params.time else END_OF_DAY
            due = datetime(day.year, day.month, day.day, hour, minute)
            if params.time and due <= now:
                return ToolResult.fail("Esa hora ya ha pasado")
            if params.time and ctx.alarms is not None:
                alarm_id = ctx.alarms.add("alarm", due.timestamp(), label=params.text).id
        task = store.add_task(params.text, due.timestamp() if due else None, alarm_id)

        async def back() -> str:
            store.delete_task(task.id)
            if alarm_id and ctx.alarms is not None:
                ctx.alarms.cancel(alarm_id)
            return "Tarea quitada"

        when = self._when(due, now, with_time=bool(params.time))
        return ToolResult(
            ok=True,
            message=f"Tarea apuntada: {task.text}" + (f" ({when})" if when else "") + ".",
            display="Tarea apuntada",
            secondary=task.text + (f" · {when}" if when else ""),
            undo=Undo("Apuntar la tarea", back),
        )

    def _close(
        self, store: OrganizerStore, task: Task, ctx: ToolContext, *, done: bool
    ) -> ToolResult:
        if done:
            store.finish_task(task.id)
        else:
            store.delete_task(task.id)
        # El aviso ya no hace falta (y si se deshace, vuelve si aún no ha pasado).
        if task.alarm_id and ctx.alarms is not None:
            ctx.alarms.cancel(task.alarm_id)

        async def back() -> str:
            if done:
                store.finish_task(task.id, False)
            else:
                store.delete_task(task.id, False)
            alarms = ctx.alarms
            if task.alarm_id and task.due and alarms is not None and task.due > alarms.clock():
                alarms.add("alarm", task.due, label=task.text)
            return "Tarea pendiente otra vez"

        verb = "hecha" if done else "borrada"
        return ToolResult(
            ok=True,
            message=f"Tarea {verb}: {task.text}.",
            undo=Undo(f"Tarea {verb}", back),
        )

    def _read(self, store: OrganizerStore, params: TaskParams, now: datetime) -> ToolResult:
        day = self._day(params, now)
        until = (
            datetime(day.year, day.month, day.day, *END_OF_DAY).timestamp()
            if day is not None
            else None
        )
        pending = store.tasks(until=until)
        if not pending:
            when = " para ese día" if day is not None else ""
            return ToolResult(ok=True, message=f"No tienes tareas pendientes{when}.", speak=True)
        parts = []
        for t in pending:
            when = self._when(
                datetime.fromtimestamp(t.due) if t.due else None,
                now,
                with_time=bool(t.alarm_id),
            )
            parts.append(f"{t.text} ({when})" if when else t.text)
        count = f"{len(pending)} tarea" + ("s" if len(pending) > 1 else "")
        return ToolResult(
            ok=True,
            message=f"Tienes {count}: {spoken_join(parts)}.",
            display=f"{count[0].upper()}{count[1:]}",
            secondary=", ".join(parts)[:300],
            speak=True,
        )

    @staticmethod
    def _when(due: datetime | None, now: datetime, *, with_time: bool) -> str:
        if due is None:
            return ""
        label = day_label(due, now)
        return f"{label} a las {due:%H:%M}" if with_time else label
