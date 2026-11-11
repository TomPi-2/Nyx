"""set_alarm: alarma a una hora, con texto opcional para usarla de recordatorio (verde).

Hoy a esa hora, o mañana si ya pasó (SPEC sección 7). Suena aunque se esté en partida.
Deshacer = cancelarla.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from nyx.alarms.spoken import day_label, next_occurrence
from nyx.safety.undo import Undo
from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult


class SetAlarmParams(Params):
    time: str = Field(pattern=r"^([01]?\d|2[0-3]):[0-5]\d$", description="Hora 24 h (HH:MM)")
    day: Literal["today", "tomorrow"] | None = Field(default=None, description="Día (hoy o mañana)")
    label: str = Field(default="", max_length=100, description="Texto del recordatorio")


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
        alarm = alarms.add("alarm", due.timestamp(), label=params.label)

        async def cancel() -> str:
            alarms.cancel(alarm.id)
            return "Alarma cancelada"

        at = due.strftime("%H:%M")
        what = "Recordatorio" if params.label else "Alarma"
        secondary = day_label(due, now) + (f" · {params.label}" if params.label else "")
        return ToolResult(
            ok=True,
            message=f"{what} a las {at} ({day_label(due, now)})",
            display=f"{what} {at}",
            secondary=secondary,
            data={"alarm_id": alarm.id, "due": alarm.due},
            undo=Undo(f"{what} de las {at}", cancel),
        )
