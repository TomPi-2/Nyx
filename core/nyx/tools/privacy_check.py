"""privacy_check: quién usa (o ha usado) el micrófono y la cámara (tarea 8.07). Verde.

«¿Quién está usando el micro?», «¿alguien me está escuchando?», «¿qué apps han usado la cámara
hoy?». Lee el registro de privacidad de Windows (`winapi/privacy.py`); no cambia nada. Si es
Nyx quien usa el micrófono, lo dice («yo, para oírte»).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Literal

from pydantic import Field

from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult
from nyx.tools.list_items import spoken_join
from nyx.winapi.privacy import Capability, Use, uses

Device = Literal["microphone", "camera", "both"]
When = Literal["now", "today", "recent"]

_CAPS: dict[str, tuple[Capability, str]] = {
    "microphone": ("microphone", "el micrófono"),
    "camera": ("webcam", "la cámara"),
}


class PrivacyCheckParams(Params):
    device: Device = Field(default="both", description="microphone, camera o both")
    when: When = Field(default="now", description="now (ahora), today (hoy) o recent (7 días)")


class PrivacyCheck(Tool[PrivacyCheckParams]):
    name = "privacy_check"
    description = "Dice qué apps usan ahora (o han usado) el micrófono o la cámara."
    risk = Risk.GREEN
    game_policy = GamePolicy.ALLOWED
    category = Category.SYSTEM
    params_model = PrivacyCheckParams
    observe = True

    def __init__(self, reader: Callable[[Capability], list[Use]] = uses) -> None:
        self._read = reader

    async def run(self, params: PrivacyCheckParams, ctx: ToolContext) -> ToolResult:
        import asyncio

        devices = ["microphone", "camera"] if params.device == "both" else [params.device]
        now = datetime.now()
        since = {
            "now": None,
            "today": now.replace(hour=0, minute=0, second=0, microsecond=0),
            "recent": now - timedelta(days=7),
        }[params.when]
        lines: list[str] = []
        for device in devices:
            cap, label = _CAPS[device]
            found = await asyncio.to_thread(self._read, cap)
            lines.append(self._line(label, found, since, now))
        message = " ".join(lines)
        return ToolResult(ok=True, message=message, display=lines[0][:120], speak=True)

    @staticmethod
    def _line(label: str, found: list[Use], since: datetime | None, now: datetime) -> str:
        active = [u for u in found if u.in_use]
        names = ["yo, para oírte" if u.is_nyx else u.name for u in active]
        if since is None:
            if not names:
                return f"Nadie está usando {label} ahora mismo."
            return f"Ahora mismo usa {label}: {spoken_join(names)}."
        recent = [u for u in found if not u.in_use and u.last and u.last >= since]
        parts = [f"{n} (ahora)" for n in names]
        for u in recent[:8]:
            when = (
                f"a las {u.last:%H:%M}"
                if u.last and u.last.date() == now.date()
                else (f"el {u.last:%d/%m}" if u.last else "")
            )
            parts.append(f"{'yo' if u.is_nyx else u.name} ({when})")
        period = "hoy" if since.date() == now.date() else "esta semana"
        if not parts:
            return f"Nadie ha usado {label} {period}."
        return f"Han usado {label} {period}: {spoken_join(parts)}."
