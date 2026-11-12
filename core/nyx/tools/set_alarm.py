"""set_alarm: alarma a una hora, con texto opcional para usarla de recordatorio (verde).

Hoy a esa hora, o mañana si ya pasó (SPEC sección 7). Suena aunque se esté en partida.
Puede repetirse todos los días, de lunes a viernes o los fines de semana (6.12).
Deshacer = cancelarla.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from nyx.alarms.scheduler import first_matching_day
from nyx.alarms.spoken import day_label, next_occurrence
from nyx.alarms.store import Repeat
from nyx.safety.undo import Undo
from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult

REPEAT_LABELS: dict[Repeat, str] = {
    "none": "",
    "daily": "todos los días",
    "weekdays": "de lunes a viernes",
    "weekends": "los fines de semana",
}


class SetAlarmParams(Params):
    time: str = Field(pattern=r"^([01]?\d|2[0-3]):[0-5]\d$", description="Hora 24 h (HH:MM)")
    day: Literal["today", "tomorrow"] | None = Field(default=None, description="Día (hoy o mañana)")
    label: str = Field(default="", max_length=100, description="Texto del recordatorio")
    repeat: Repeat = Field(default="none", description="Repetir: daily, weekdays o weekends")


class SetAlarm(Tool[SetAlarmParams]):
    name = "set_alarm"
    description = "Pone alarma o recordatorio. Ej.: «alarma a las 7:30» (time=07:30)."
    risk = Risk.GREEN
    game_policy = GamePolicy.ALLOWED
    category = Category.TIME
    params_model = SetAlarmParams

    async def run(self, params: SetAlarmParams, ctx: ToolContext) -> ToolResult:
        if ctx.alarms is None:
            return ToolResult.fail("Las alarmas no están disponibles")
        alarms = ctx.alarms
        hour, minute = (int(x) for x in params.time.split(":"))
        now = datetime.fromtimestamp(alarms.clock())
        due = next_occurrence(hour, minute, now, tomorrow=params.day == "tomorrow")
        due = first_matching_day(due, params.repeat)  # «de lunes a viernes» un sábado → lunes
        alarm = alarms.add("alarm", due.timestamp(), label=params.label, repeat=params.repeat)

        async def cancel() -> str:
            alarms.cancel(alarm.id)
            return "Alarma cancelada"

        at = due.strftime("%H:%M")
        what = "Recordatorio" if params.label else "Alarma"
        when = day_label(due, now)
        repeat = REPEAT_LABELS[params.repeat]
        if repeat:
            when = f"{repeat}, desde {when}"
        secondary = when + (f" · {params.label}" if params.label else "")
        return ToolResult(
            ok=True,
            message=f"{what} a las {at} ({when})",
            display=f"{what} {at}",
            secondary=secondary,
            data={"alarm_id": alarm.id, "due": alarm.due, "repeat": params.repeat},
            undo=Undo(f"{what} de las {at}", cancel),
        )
