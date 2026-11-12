"""list_alarms y cancel_alarm: ver y quitar alarmas, temporizadores y recordatorios (verdes).

«¿Qué alarmas tengo?», «¿cuánto le queda al temporizador?», «quita la alarma de las 7».
Nyx ya no puede decir «no tienes alarmas» sin mirarlo (ERRORES.md, 2026-11-11: lo dijo con
una puesta).
"""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import Field

from nyx.alarms.spoken import day_label, spoken_duration
from nyx.alarms.store import Alarm
from nyx.index.aliases import normalize
from nyx.tools.base import (
    Category,
    GamePolicy,
    Params,
    Risk,
    Tool,
    ToolContext,
    ToolResult,
)
from nyx.tools.set_alarm import REPEAT_LABELS

MAX_LISTED = 8


def describe_alarm(alarm: Alarm, now: datetime) -> str:
    """«temporizador de 5 min: quedan 3 minutos» · «alarma a las 07:30 (mañana): llamar a mamá»."""
    due = datetime.fromtimestamp(alarm.due)
    left = max(0, int(alarm.due - now.timestamp()))
    if alarm.kind == "timer":
        what = "temporizador"
        if alarm.duration_s:
            what += f" de {spoken_duration(alarm.duration_s)}"
    else:
        what = f"{'recordatorio' if alarm.label else 'alarma'} a las {due:%H:%M}"
        what += f" ({day_label(due, now)})"
        if repeat := REPEAT_LABELS[alarm.repeat]:
            what += f", {repeat}"
    label = f" «{alarm.label}»" if alarm.label else ""
    return f"{what}{label}: quedan {spoken_duration(left)}"


class ListAlarmsParams(Params):
    pass


class ListAlarms(Tool[ListAlarmsParams]):
    name = "list_alarms"
    description = "Lista alarmas y temporizadores pendientes. Ej.: «¿qué alarmas tengo?»."
    risk = Risk.GREEN
    game_policy = GamePolicy.ALLOWED
    category = Category.TIME
    params_model = ListAlarmsParams
    observe = True

    async def run(self, params: ListAlarmsParams, ctx: ToolContext) -> ToolResult:
        if ctx.alarms is None:
            return ToolResult.fail("Las alarmas no están disponibles")
        pending = ctx.alarms.pending()
        if not pending:
            return ToolResult(
                ok=True, message="No tienes alarmas ni temporizadores", display="Nada pendiente"
            )
        now = datetime.fromtimestamp(ctx.alarms.clock())
        lines = [describe_alarm(a, now) for a in pending[:MAX_LISTED]]
        more = f" y {len(pending) - MAX_LISTED} más" if len(pending) > MAX_LISTED else ""
        count = "1 pendiente" if len(pending) == 1 else f"{len(pending)} pendientes"
        return ToolResult(
            ok=True,
            message=f"{count}: " + "; ".join(lines) + more,
            display=count[0].upper() + count[1:],
            secondary=lines[0],
            data={"ids": [a.id for a in pending]},
        )


class CancelAlarmParams(Params):
    which: str = Field(
        default="",
        max_length=100,
        description="Hora, texto o «todas»",
    )


def pick(pending: list[Alarm], which: str) -> list[Alarm]:
    """Las alarmas a las que se refiere `which` (vacío: la única que haya)."""
    want = normalize(which)
    if not want:
        return pending if len(pending) == 1 else []
    if want in ("todas", "todos", "todas las alarmas", "todo"):
        return pending
    # Horas tal como se escriben («7», «07:30», «7.30»), antes de normalizar el texto.
    asked_times = set(re.findall(r"\d{1,2}(?:[:.]\d{2})?", which.replace(".", ":")))
    hits: list[Alarm] = []
    for alarm in pending:
        due = datetime.fromtimestamp(alarm.due)
        times = {f"{due:%H:%M}", f"{due.hour}:{due.minute:02d}"}
        if due.minute == 0:
            times |= {f"{due:%H}", str(due.hour)}
        if (
            asked_times & times
            or (alarm.kind == "timer" and "temporizador" in want)
            or (alarm.label and normalize(alarm.label) in want)
            or (alarm.label and want in normalize(alarm.label))
        ):
            hits.append(alarm)
    return hits


class CancelAlarm(Tool[CancelAlarmParams]):
    name = "cancel_alarm"
    description = "Quita alarma o temporizador. Ej.: «quita la alarma de las 7» (which=07:00)."
    risk = Risk.GREEN
    game_policy = GamePolicy.ALLOWED
    category = Category.TIME
    params_model = CancelAlarmParams

    async def run(self, params: CancelAlarmParams, ctx: ToolContext) -> ToolResult:
        if ctx.alarms is None:
            return ToolResult.fail("Las alarmas no están disponibles")
        pending = ctx.alarms.pending()
        if not pending:
            return ToolResult.fail("No tienes alarmas ni temporizadores")
        chosen = pick(pending, params.which)
        if not chosen:
            now = datetime.fromtimestamp(ctx.alarms.clock())
            options = "; ".join(describe_alarm(a, now) for a in pending[:3])
            return ToolResult.fail("¿Cuál quito?", options)
        for alarm in chosen:
            ctx.alarms.cancel(alarm.id)
        what = "1 quitada" if len(chosen) == 1 else f"{len(chosen)} quitadas"
        return ToolResult(ok=True, message=f"Hecho: {what}", display=what[0].upper() + what[1:])
