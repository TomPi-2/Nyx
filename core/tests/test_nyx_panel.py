"""nyx_panel (9.11): saca el panel de su color, su tamaño o los paneles junto a Nyx."""

from __future__ import annotations

import pytest

from nyx.tools.base import GamePolicy, Risk, ToolContext
from nyx.tools.nyx_panel import NyxPanel, NyxPanelParams
from nyx.tools.registry import default_registry


@pytest.mark.parametrize(
    ("panel", "mode"), [("color", "color"), ("tamaño", "size"), ("paneles", "tint")]
)
async def test_opens_the_panel(panel: str, mode: str, ctx: ToolContext) -> None:
    opened: list[str] = []

    async def open_panel(m: str) -> None:
        opened.append(m)

    ctx.open_nyx_panel = open_panel
    result = await NyxPanel().run(NyxPanelParams(panel=panel), ctx)  # type: ignore[arg-type]
    assert result.ok and opened == [mode]
    assert not result.display and not result.speak  # lo dice Nyx desde el panel


async def test_without_interface_it_says_so(ctx: ToolContext) -> None:
    result = await NyxPanel().run(NyxPanelParams(panel="color"), ctx)
    assert not result.ok


def test_router_only_green_and_deferred_in_game() -> None:
    tool = NyxPanel()
    assert tool.risk is Risk.GREEN and tool.game_policy is GamePolicy.DEFERRED
    assert not tool.llm_visible  # el modelo entrenado no la ve (6.27)
    registry = default_registry()
    assert registry.get("nyx_panel") is not None
    assert "nyx_panel" not in [s["function"]["name"] for s in registry.schemas()]
