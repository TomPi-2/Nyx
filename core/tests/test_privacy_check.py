"""8.07: quién usa (o ha usado) el micrófono y la cámara."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest

from nyx.brain.router import Route, route
from nyx.index.service import SystemIndex
from nyx.tools.base import ToolContext
from nyx.tools.privacy_check import PrivacyCheck, PrivacyCheckParams
from nyx.winapi.privacy import Use, _filetime, _package_name

NOW = datetime.now()


def reader(mic: list[Use], cam: list[Use] | None = None) -> Any:
    return lambda cap: mic if cap == "microphone" else (cam or [])


def test_store_package_names_and_filetime() -> None:
    assert _package_name("5319275A.WhatsAppDesktop_cv1g1gvanyjgm") == "WhatsApp Desktop"
    assert _package_name("Microsoft.WindowsCamera_8wekyb3d8bbwe") == "Cámara de Windows"
    assert _filetime(0) is None
    assert _filetime(125911584000000000) == datetime(2000, 1, 1)  # FILETIME conocido (UTC)


async def test_who_is_using_it_now(ctx: ToolContext) -> None:
    tool = PrivacyCheck(reader([Use("Discord", True, NOW), Use("Nyx", True, NOW, is_nyx=True)]))
    result = await tool.run(PrivacyCheckParams(device="microphone"), ctx)
    assert result.speak and result.message == (
        "Ahora mismo usa el micrófono: Discord y yo, para oírte."
    )
    nobody = await PrivacyCheck(reader([])).run(PrivacyCheckParams(device="camera"), ctx)
    assert nobody.message == "Nadie está usando la cámara ahora mismo."


async def test_who_used_it_today(ctx: ToolContext) -> None:
    earlier = NOW.replace(hour=0, minute=1) if NOW.hour else NOW
    old = NOW - timedelta(days=3)
    tool = PrivacyCheck(
        reader([Use("Zoom", False, earlier), Use("Skype", False, old)], [Use("OBS", True, NOW)])
    )
    result = await tool.run(PrivacyCheckParams(device="both", when="today"), ctx)
    assert "Han usado el micrófono hoy: Zoom (a las" in result.message
    assert "Skype" not in result.message
    assert "Han usado la cámara hoy: OBS (ahora)." in result.message
    week = await tool.run(PrivacyCheckParams(device="microphone", when="recent"), ctx)
    assert "Skype (el " in week.message and "esta semana" in week.message


@pytest.mark.parametrize(
    ("text", "args"),
    [
        ("¿quién está usando el micro?", {"device": "microphone", "when": "now"}),
        ("¿qué apps están usando la cámara?", {"device": "camera", "when": "now"}),
        ("¿alguien me está escuchando?", {"device": "microphone", "when": "now"}),
        ("¿se está usando la webcam ahora mismo?", {"device": "camera", "when": "now"}),
        ("¿qué programas han usado el micrófono hoy?", {"device": "microphone", "when": "today"}),
        ("¿quién ha usado la cámara esta semana?", {"device": "camera", "when": "recent"}),
    ],
)
def test_router(index: SystemIndex, text: str, args: dict[str, str]) -> None:
    routed = route(text, index)
    assert isinstance(routed, Route) and routed.rule.startswith("privacy_")
    (call,) = routed.calls
    assert call.name == "privacy_check" and call.arguments == args
