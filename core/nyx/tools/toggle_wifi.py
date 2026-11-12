"""toggle_wifi: activa, desactiva o alterna el Wi-Fi (amarilla, diferida en partida).

Deshacer vuelve a dejar el adaptador en el estado que tenía antes del cambio.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from pydantic import Field

from nyx.safety.undo import Undo
from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult

log = logging.getLogger(__name__)

RadioSwitcher = Callable[[bool | None], tuple[bool, bool]]


async def _switch_winrt_radio(kind_name: str, enabled: bool | None) -> tuple[bool, bool]:
    from winrt.windows.devices.radios import Radio, RadioAccessStatus, RadioKind, RadioState

    target_kind = RadioKind.WI_FI if kind_name == "wifi" else RadioKind.BLUETOOTH
    access = await Radio.request_access_async()
    if access != RadioAccessStatus.ALLOWED:
        raise PermissionError(f"RadioAccessStatus={access}")
    radios = [r for r in await Radio.get_radios_async() if r.kind == target_kind]
    if not radios:
        raise LookupError(kind_name)
    was_on = any(r.state == RadioState.ON for r in radios)
    new_on = (not was_on) if enabled is None else enabled
    desired = RadioState.ON if new_on else RadioState.OFF
    for radio in radios:
        status = await radio.set_state_async(desired)
        if status != RadioAccessStatus.ALLOWED:
            raise PermissionError(f"set_state_async={status}")
    return new_on, was_on


def switch_wifi(enabled: bool | None = None) -> tuple[bool, bool]:
    """Cambia el estado del Wi-Fi y devuelve `(nuevo_estado, estado_anterior)`."""
    return asyncio.run(_switch_winrt_radio("wifi", enabled))


async def run_radio_toggle(
    label: str,
    enabled: bool | None,
    switcher: RadioSwitcher,
) -> ToolResult:
    try:
        new_on, was_on = await asyncio.to_thread(switcher, enabled)
    except LookupError:
        return ToolResult.fail(f"No encuentro ningún adaptador {label} en el equipo")
    except PermissionError:
        return ToolResult.fail(f"Windows no permite cambiar el {label}")
    except Exception:
        log.warning("No se pudo cambiar el estado de %s", label, exc_info=True)
        return ToolResult.fail(f"No he podido cambiar el {label}")

    state_word = "activado" if new_on else "desactivado"
    action_word = "Activar" if new_on else "Desactivar"

    async def restore() -> str:
        await asyncio.to_thread(switcher, was_on)
        return f"{label} {'activado' if was_on else 'desactivado'}"

    msg = f"{label} {state_word}"
    return ToolResult(
        ok=True,
        message=msg,
        display=msg,
        data={"enabled": new_on, "previous": was_on},
        undo=Undo(f"{action_word} {label}", restore),
    )


class ToggleWifiParams(Params):
    enabled: bool | None = Field(
        default=None,
        description="True=activar, False=desactivar (vacío=alternar)",
    )


class ToggleWifi(Tool[ToggleWifiParams]):
    name = "toggle_wifi"
    description = (
        "Activa o desactiva el Wi-Fi. "
        "Ej.: «desactiva el wifi» (enabled=false), «activa el wifi» (enabled=true)."
    )
    risk = Risk.YELLOW
    game_policy = GamePolicy.DEFERRED
    category = Category.SYSTEM
    params_model = ToggleWifiParams

    def __init__(self, switcher: RadioSwitcher = switch_wifi) -> None:
        self._switcher = switcher

    async def run(self, params: ToggleWifiParams, ctx: ToolContext) -> ToolResult:
        return await run_radio_toggle("Wi-Fi", params.enabled, self._switcher)
