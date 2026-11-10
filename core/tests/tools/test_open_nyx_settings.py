"""open_nyx_settings: abre la ventana de Ajustes de Nyx."""

from dataclasses import replace

import pytest

from nyx.index.service import SystemIndex
from nyx.tools.base import GamePolicy, Risk, ToolContext
from nyx.tools.open_nyx_settings import OpenNyxSettings, OpenNyxSettingsParams
from tests.test_router import call


async def test_opens_the_window_in_a_section(ctx: ToolContext) -> None:
    opened: list[str | None] = []

    async def open_window(section: str | None) -> None:
        opened.append(section)

    tool = OpenNyxSettings()
    ctx = replace(ctx, open_nyx_settings=open_window)
    result = await tool.run(OpenNyxSettingsParams(section="partida"), ctx)
    assert result.ok
    await tool.run(OpenNyxSettingsParams(), ctx)
    assert opened == ["partida", None]


async def test_without_interface_it_fails_clearly(ctx: ToolContext) -> None:
    result = await OpenNyxSettings().run(OpenNyxSettingsParams(), ctx)
    assert not result.ok


def test_is_green_and_waits_for_the_game() -> None:
    assert OpenNyxSettings.risk is Risk.GREEN
    assert OpenNyxSettings.game_policy is GamePolicy.DEFERRED


@pytest.mark.parametrize(
    ("text", "section"),
    [
        ("abre tus ajustes", None),
        ("Abre los ajustes de Nyx", None),
        ("abre la configuración de nix", None),
        ("ajustes de Nyx", None),
        ("muéstrame tus ajustes del modo partida", "partida"),
        ("abre tu configuración de apariencia", "apariencia"),
        ("abre tus opciones de respuestas", "respuestas"),
        ("abre tus ajustes de voz", "voz"),
        ("tu configuración del micrófono", "voz"),
        ("abre tus ajustes de la palabra de activación", "activacion"),
        ("abre tus ajustes del modelo", "cerebro"),
        ("abre tus ajustes de privacidad", "privacidad"),
    ],
)
def test_router_opens_nyx_settings(text: str, section: str | None, index: SystemIndex) -> None:
    tool, args = call(text, index)
    assert tool == "open_nyx_settings"
    assert args.get("section") == section


@pytest.mark.parametrize(
    "text", ["abre los ajustes de sonido", "abre la configuración", "abre los ajustes"]
)
def test_windows_settings_are_not_confused(text: str, index: SystemIndex) -> None:
    tool, _ = call(text, index)
    assert tool == "open_settings"
