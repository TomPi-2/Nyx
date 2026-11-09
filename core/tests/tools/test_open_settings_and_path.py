from pathlib import Path

from nyx.tools.base import ToolContext
from nyx.tools.open_path import OpenPath, OpenPathParams
from nyx.tools.open_settings import OpenSettings, OpenSettingsParams
from tests.tools.fakes import FakeDesktop


async def test_settings_page(ctx: ToolContext, desktop: FakeDesktop) -> None:
    result = await OpenSettings().run(OpenSettingsParams(page="raton"), ctx)
    assert result.ok
    assert desktop.opened == ["ms-settings:mousetouchpad"]


async def test_settings_root(ctx: ToolContext, desktop: FakeDesktop) -> None:
    result = await OpenSettings().run(OpenSettingsParams(), ctx)
    assert result.ok
    assert desktop.opened == ["ms-settings:"]


async def test_settings_unknown(ctx: ToolContext, desktop: FakeDesktop) -> None:
    result = await OpenSettings().run(OpenSettingsParams(page="impresora 3d de marte"), ctx)
    assert not result.ok


async def test_open_known_folder(ctx: ToolContext, desktop: FakeDesktop) -> None:
    result = await OpenPath().run(OpenPathParams(target="descargas"), ctx)
    assert result.ok
    assert desktop.opened[0].endswith("Descargas")


async def test_open_absolute_path(ctx: ToolContext, desktop: FakeDesktop, tmp_path: Path) -> None:
    result = await OpenPath().run(OpenPathParams(target=str(tmp_path)), ctx)
    assert result.ok
    assert desktop.opened == [str(tmp_path)]


async def test_missing_path(ctx: ToolContext, desktop: FakeDesktop, tmp_path: Path) -> None:
    result = await OpenPath().run(OpenPathParams(target=str(tmp_path / "no-existe")), ctx)
    assert not result.ok
    assert desktop.opened == []
