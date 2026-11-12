"""stopwatch: cronómetro en memoria (start, stop, status) · verde, permitido en partida."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Literal

from pydantic import Field

from nyx.alarms.spoken import short_duration, spoken_duration
from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult

StopwatchAction = Literal["start", "stop", "status"]


def _format_spoken(seconds: int) -> str:
    return "0 segundos" if seconds == 0 else spoken_duration(seconds)


class StopwatchParams(Params):
    action: StopwatchAction = Field(description="Acción (start, stop o status)")


class Stopwatch(Tool[StopwatchParams]):
    name = "stopwatch"
    description = (
        "Controla un cronómetro. Ej.: «empieza un cronómetro» (action=start), "
        "«¿cuánto lleva?» (action=status), «para el cronómetro» (action=stop)."
    )
    risk = Risk.GREEN
    game_policy = GamePolicy.ALLOWED
    category = Category.TIME
    params_model = StopwatchParams
    observe = True

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._started_at: float | None = None
        self._last_elapsed: int | None = None

    async def run(self, params: StopwatchParams, ctx: ToolContext) -> ToolResult:
        if params.action == "start":
            self._started_at = self._clock()
            self._last_elapsed = None
            return ToolResult(
                ok=True,
                message="Cronómetro en marcha.",
                display="Cronómetro en marcha",
                secondary="0 s",
                observe=False,  # no hay nada que contar: sin vuelta al LLM, como un temporizador
                data={"running": True, "elapsed_s": 0},
            )

        if params.action == "status":
            if self._started_at is not None:
                elapsed = max(0, int(self._clock() - self._started_at))
                return ToolResult(
                    ok=True,
                    message=f"El cronómetro lleva {_format_spoken(elapsed)}.",
                    display=short_duration(elapsed),
                    secondary="en marcha",
                    data={"running": True, "elapsed_s": elapsed},
                )
            if self._last_elapsed is not None:
                return ToolResult(
                    ok=True,
                    message=f"El cronómetro está parado en {_format_spoken(self._last_elapsed)}.",
                    display=short_duration(self._last_elapsed),
                    secondary="parado",
                    data={"running": False, "elapsed_s": self._last_elapsed},
                )
            return ToolResult(
                ok=True,
                message="No hay ningún cronómetro en marcha.",
                display="Sin iniciar",
                data={"running": False, "elapsed_s": 0},
            )

        if self._started_at is None:
            return ToolResult.fail("El cronómetro no está en marcha")

        elapsed = max(0, int(self._clock() - self._started_at))
        self._started_at = None
        self._last_elapsed = elapsed
        return ToolResult(
            ok=True,
            message=f"Cronómetro parado en {_format_spoken(elapsed)}.",
            display=short_duration(elapsed),
            secondary="parado",
            data={"running": False, "elapsed_s": elapsed},
        )
