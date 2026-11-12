"""toggle_bluetooth: activa, desactiva o alterna el Bluetooth (amarilla, diferida en partida).

Deshacer vuelve a dejar el adaptador en el estado que tenía antes del cambio.
"""

from __future__ import annotations

import asyncio

from pydantic import Field

from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult
from nyx.tools.toggle_wifi import RadioSwitcher, _switch_winrt_radio, run_radio_toggle


def switch_bluetooth(enabled: bool | None = None) -> tuple[bool, bool]:
    """Cambia el estado del Bluetooth y devuelve `(nuevo_estado, estado_anterior)`."""
    return asyncio.run(_switch_winrt_radio("bluetooth", enabled))


class ToggleBluetoothParams(Params):
    enabled: bool | None = Field(
        default=None,
        description="True=activar, False=desactivar (vacío=alternar)",
    )


class ToggleBluetooth(Tool[ToggleBluetoothParams]):
    name = "toggle_bluetooth"
    description = (
        "Activa o desactiva el Bluetooth. "
        "Ej.: «apaga el bluetooth» (enabled=false), «enciende el bluetooth» (enabled=true)."
    )
    risk = Risk.YELLOW
    game_policy = GamePolicy.DEFERRED
    category = Category.SYSTEM
    params_model = ToggleBluetoothParams

    def __init__(self, switcher: RadioSwitcher = switch_bluetooth) -> None:
        self._switcher = switcher

    async def run(self, params: ToggleBluetoothParams, ctx: ToolContext) -> ToolResult:
        return await run_radio_toggle("Bluetooth", params.enabled, self._switcher)
