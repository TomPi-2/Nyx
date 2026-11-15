"""«Nyx, actualízate» (9.06): la herramienta, su regla y el coordinador."""

from __future__ import annotations

from typing import Any

import pytest

from nyx.brain.router import Route, route
from nyx.bus import EventBus
from nyx.events import UpdateApply, UpdateOffered
from nyx.index.service import SystemIndex
from nyx.settings.model import Settings
from nyx.tools.base import GamePolicy, ToolContext
from nyx.tools.nyx_update import NyxUpdate, NyxUpdateParams
from nyx.update import coordinator as coord
from nyx.update.coordinator import UpdateCoordinator
from nyx.update.moment import UpdateGate


@pytest.mark.parametrize(
    "text", ["actualízate", "instala la actualización", "actualiza Nyx", "ponte al día"]
)
def test_rule(text: str, index: SystemIndex) -> None:
    routed = route(text, index)
    assert isinstance(routed, Route) and [c.name for c in routed.calls] == ["nyx_update"]


@pytest.mark.parametrize("text", ["actualiza Chrome", "actualiza el driver de la gráfica"])
def test_not_other_updates(text: str, index: SystemIndex) -> None:
    routed = route(text, index)
    assert not isinstance(routed, Route) or "nyx_update" not in [c.name for c in routed.calls]


async def test_tool(ctx: ToolContext) -> None:
    tool = NyxUpdate()
    assert tool.game_policy is GamePolicy.DEFERRED and not tool.llm_visible
    assert not (await tool.run(NyxUpdateParams(), ctx)).ok

    async def now() -> str:
        return "Me actualizo a la 1.4.0. Vuelvo enseguida."

    ctx.update_now = now
    result = await tool.run(NyxUpdateParams(), ctx)
    assert result.ok and result.speak and "1.4.0" in result.message


async def test_by_voice(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(coord, "VOICE_DELAY_S", 0)
    bus = EventBus()
    applied: list[Any] = []

    async def on_apply(e: UpdateApply) -> None:
        applied.append(e)

    bus.subscribe(UpdateApply, on_apply)
    c = UpdateCoordinator(bus, Settings(), UpdateGate(), backup=lambda _v: None, poll_s=3600)
    assert await c.by_voice() == "Ya tienes la última versión."
    await bus.publish(UpdateOffered("1.4.0"))
    assert "1.4.0" in await c.by_voice()
    assert c._voice is not None
    await c._voice
    assert [a.version for a in applied] == ["1.4.0"]
    c.close()
