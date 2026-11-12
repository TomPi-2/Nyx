"""set_brightness: cambia el brillo de la pantalla (verde, permitida en partida).

Usa `screen-brightness-control` (MIT). En monitores externos sin DDC/CI activado puede no
funcionar y lo avisa.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Self

from pydantic import Field, model_validator

from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult

log = logging.getLogger(__name__)

DEFAULT_STEP = 20
_DDC_HINT = "En monitores externos sin DDC/CI puede no funcionar"


def get_screen_brightness() -> int | None:
    """Brillo actual (0–100) del primer monitor compatible, o None."""
    import screen_brightness_control as sbc

    values = sbc.get_brightness()
    for val in values:
        if isinstance(val, int):
            return max(0, min(100, val))
    return None


def set_screen_brightness(level: int) -> int | None:
    """Ajusta el brillo (0–100) y devuelve el valor final, o None si ningún monitor responde."""
    import screen_brightness_control as sbc

    clamped = max(0, min(100, level))
    values = sbc.set_brightness(clamped, no_return=False)
    if values:
        for val in values:
            if isinstance(val, int):
                return max(0, min(100, val))
    current = get_screen_brightness()
    return current if current is not None else clamped


class SetBrightnessParams(Params):
    level: int | None = Field(default=None, ge=0, le=100, description="Nivel (0–100)")
    change: int | None = Field(default=None, ge=-100, le=100, description="Subir o bajar")

    @model_validator(mode="after")
    def one_action(self) -> Self:
        if self.level is None and self.change is None:
            raise ValueError("indica level o change")
        if self.level is not None and self.change is not None:
            raise ValueError("level y change no van juntos")
        return self


class SetBrightness(Tool[SetBrightnessParams]):
    name = "set_brightness"
    description = (
        "Cambia el brillo de la pantalla. "
        "Ej.: «pon el brillo al 50» (level=50), «baja el brillo» (change=-20)."
    )
    risk = Risk.GREEN
    game_policy = GamePolicy.ALLOWED
    category = Category.SYSTEM
    params_model = SetBrightnessParams

    def __init__(
        self,
        *,
        getter: Callable[[], int | None] = get_screen_brightness,
        setter: Callable[[int], int | None] = set_screen_brightness,
    ) -> None:
        self._getter = getter
        self._setter = setter

    async def run(self, params: SetBrightnessParams, ctx: ToolContext) -> ToolResult:
        try:
            target = params.level
            if params.change is not None:
                current = await asyncio.to_thread(self._getter)
                if current is None:
                    return ToolResult.fail("No he podido cambiar el brillo", _DDC_HINT)
                target = max(0, min(100, current + params.change))
            assert target is not None
            final = await asyncio.to_thread(self._setter, target)
        except Exception:
            log.warning("No se pudo cambiar el brillo de la pantalla", exc_info=True)
            return ToolResult.fail("No he podido cambiar el brillo", _DDC_HINT)
        if final is None:
            return ToolResult.fail("No he podido cambiar el brillo", _DDC_HINT)
        return ToolResult(ok=True, message=f"Brillo {final}", data={"level": final})
