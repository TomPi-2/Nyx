"""set_timer: temporizador, con texto opcional para usarlo de recordatorio (verde).

Suena aunque se esté en partida (SPEC sección 9). Deshacer = cancelarlo.
"""

from __future__ import annotations

from datetime import datetime
from typing import Self

from pydantic import Field, model_validator

from nyx.alarms.spoken import short_duration
from nyx.safety.undo import Undo
from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult

MAX_S = 24 * 3600


class SetTimerParams(Params):
    hours: int = Field(default=0, ge=0, le=24)
    minutes: int = Field(default=0, ge=0, le=24 * 60)
    seconds: int = Field(default=0, ge=0, le=3600)
    label: str = Field(default="", max_length=100, description="Qué recordar al sonar")

    @model_validator(mode="after")
    def some_time(self) -> Self:
        if not 0 < self.total <= MAX_S:
            raise ValueError("la duración debe estar entre 1 segundo y 24 horas")
        return self

    @property
    def total(self) -> int:
        return self.hours * 3600 + self.minutes * 60 + self.seconds


class SetTimer(Tool[SetTimerParams]):
    name = "set_timer"
    description = (
        "Pone un temporizador. Ej.: «temporizador de 5 minutos» (minutes=5), «avísame en "
        "media hora» (minutes=30), «recuérdame en 10 minutos sacar la pizza» (minutes=10, "
        "label=sacar la pizza)."
    )
    risk = Risk.GREEN
    game_policy = GamePolicy.ALLOWED
    category = Category.TIME
    params_model = SetTimerParams

    async def run(self, params: SetTimerParams, ctx: ToolContext) -> ToolResult:
        if ctx.alarms is None:
            return ToolResult.fail("Los temporizadores no están disponibles")
        alarms = ctx.alarms
        now = alarms.clock()
        timer = alarms.add("timer", now + params.total, label=params.label, duration_s=params.total)

        async def cancel() -> str:
            alarms.cancel(timer.id)
            return "Temporizador cancelado"

        length = short_duration(params.total)
        at = datetime.fromtimestamp(timer.due).strftime("%H:%M")
        secondary = f"suena a las {at}" + (f" · {params.label}" if params.label else "")
        return ToolResult(
            ok=True,
            message=f"Temporizador de {length}",
            display=f"Temporizador {length}",
            secondary=secondary,
            data={"alarm_id": timer.id, "due": timer.due},
            undo=Undo(f"Temporizador de {length}", cancel),
        )
