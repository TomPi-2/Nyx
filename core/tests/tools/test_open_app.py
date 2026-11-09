from nyx.index.model import LaunchKind
from nyx.tools.base import Risk, ToolContext
from nyx.tools.open_app import OpenApp, OpenAppParams
from tests.tools.fakes import FakeDesktop


async def test_opens_app_and_records_use(ctx: ToolContext, desktop: FakeDesktop) -> None:
    result = await OpenApp().run(OpenAppParams(name="el vscode"), ctx)
    assert result.ok and result.display is None  # éxito silencioso
    assert desktop.launched[0].kind is LaunchKind.APPS_FOLDER
    assert desktop.launched[0].value == "Microsoft.VisualStudioCode"
    assert ctx.index.resolve("vscode")[0].score > 100  # uso registrado


async def test_opens_game_through_its_launcher(ctx: ToolContext, desktop: FakeDesktop) -> None:
    result = await OpenApp().run(OpenAppParams(name="valorant"), ctx)
    assert result.ok
    assert desktop.launched[0].value == "riot:valorant"


async def test_unknown_app_suggests(ctx: ToolContext, desktop: FakeDesktop) -> None:
    result = await OpenApp().run(OpenAppParams(name="photoshop"), ctx)
    assert not result.ok
    assert result.display == "No encuentro la app «photoshop»"
    assert desktop.launched == []


async def test_launch_error(ctx: ToolContext, desktop: FakeDesktop) -> None:
    desktop.launch_error = True
    result = await OpenApp().run(OpenAppParams(name="spotify"), ctx)
    assert not result.ok and result.display == "No he podido abrir Spotify"


def test_metadata() -> None:
    tool = OpenApp()
    assert tool.risk is Risk.GREEN
    schema = tool.schema()["function"]
    assert schema["name"] == "open_app"
    assert schema["parameters"]["required"] == ["name"]


async def test_brings_new_window_to_front(ctx: ToolContext, desktop: FakeDesktop) -> None:
    await OpenApp().run(OpenAppParams(name="vscode"), ctx)
    assert desktop.focus_requests == [("Visual Studio Code", "code.exe")]


async def test_background_does_not_focus(ctx: ToolContext, desktop: FakeDesktop) -> None:
    await OpenApp().run(OpenAppParams(name="vscode", focus=False), ctx)
    assert desktop.launched and desktop.focus_requests == []
