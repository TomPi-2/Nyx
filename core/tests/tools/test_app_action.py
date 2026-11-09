import pytest

from nyx.executor import Executor, ToolCall
from nyx.tools import app_action as action_module
from nyx.tools import app_catalog
from nyx.tools.base import ToolContext
from nyx.tools.registry import default_registry
from nyx.winapi import games, keys
from nyx.winapi.windows import Window
from tests.tools.fakes import FakeDesktop

NOTEPAD = Window(5, "Sin título: Bloc de notas", "notepad.exe")
SPOTIFY = Window(6, "Spotify Premium", "spotify.exe")
CHROME = Window(7, "YouTube - Google Chrome", "chrome.exe")
GAME = Window(8, "VALORANT", "valorant-win64-shipping.exe")


@pytest.fixture
def pressed(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []
    monkeypatch.setattr(keys, "press", lambda hk: seen.append(hk.label))
    monkeypatch.setattr(action_module, "FOCUS_SETTLE_S", 0.0)
    monkeypatch.setattr(action_module, "REPEAT_GAP_S", 0.0)
    monkeypatch.setattr(
        games, "exe_of_window", lambda h: r"C:\Riot Games\VALORANT\live\v.exe" if h == 8 else ""
    )
    return seen


def run(ctx: ToolContext, **args: object) -> object:
    return Executor(default_registry(), ctx).run(ToolCall("app_action", dict(args)))


@pytest.mark.parametrize(("language", "label"), [("es", "Ctrl+U"), ("en", "Ctrl+N")])
async def test_notepad_new_note_follows_windows_language(
    ctx: ToolContext,
    desktop: FakeDesktop,
    pressed: list[str],
    monkeypatch: pytest.MonkeyPatch,
    language: str,
    label: str,
) -> None:
    monkeypatch.setattr(action_module, "windows_language", lambda: language)
    desktop.windows, desktop.fg = [NOTEPAD], 5
    result = await run(ctx, app="Bloc de notas", action="new_tab")  # type: ignore[misc]
    assert result.ok and pressed == [label]


async def test_spotify_volume_in_background_returns_focus(
    ctx: ToolContext, desktop: FakeDesktop, pressed: list[str]
) -> None:
    desktop.windows, desktop.fg = [CHROME, SPOTIFY], 7
    result = await run(ctx, app="Spotify", action="volume_up", times=3)  # type: ignore[misc]
    assert result.ok and pressed == ["Ctrl+Up"] * 3
    assert desktop.activated == [6, 7]  # a Spotify y de vuelta a Chrome


async def test_active_window_and_unknown_action(
    ctx: ToolContext, desktop: FakeDesktop, pressed: list[str]
) -> None:
    desktop.windows, desktop.fg = [CHROME], 7
    assert (await run(ctx, action="close_tab")).ok  # type: ignore[misc]
    assert pressed == ["Ctrl+W"]
    nope = await run(ctx, action="toggle_mute")  # type: ignore[misc]
    assert not nope.ok and "no sé hacer eso" in nope.message  # type: ignore[attr-defined]


async def test_never_inside_games(
    ctx: ToolContext, desktop: FakeDesktop, pressed: list[str]
) -> None:
    desktop.windows, desktop.fg = [GAME], 8
    result = await run(ctx, action="close_tab")  # type: ignore[misc]
    assert not result.ok and "juegos" in result.message  # type: ignore[attr-defined]
    hotkey = await Executor(default_registry(), ctx).run(
        ToolCall("send_hotkey", {"keys": "ctrl+t"})
    )
    assert not hotkey.ok and pressed == []


def test_game_paths() -> None:
    assert games.is_game_exe(r"D:\SteamLibrary\steamapps\common\Elden Ring\eldenring.exe")
    assert games.is_game_exe(r"C:\Riot Games\League of Legends\LeagueClient.exe")
    assert not games.is_game_exe(r"C:\Riot Games\Riot Client\RiotClientServices.exe")
    assert not games.is_game_exe(r"C:\Program Files\Google\Chrome\Application\chrome.exe")


def test_catalog_hotkeys_are_valid_and_allowed() -> None:
    for profile in app_catalog.PROFILES:
        for action in profile.actions.values():
            for combo in action.keys.values():
                assert keys.blocked_reason(keys.parse(combo)) is None, combo


async def test_generic_browser_name_finds_any_browser(
    ctx: ToolContext, desktop: FakeDesktop, pressed: list[str]
) -> None:
    desktop.windows, desktop.fg = [NOTEPAD, CHROME], 5
    result = await run(ctx, app="Navegador", action="back")  # type: ignore[misc]
    assert result.ok and pressed == ["Alt+Left"] and desktop.activated == [7]
