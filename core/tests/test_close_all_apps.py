"""close_all_apps (paso 2 de Cerebro 2): «cierra todo», roja y enumerando lo que cierra."""

import pytest

from nyx.tools.base import Risk, ToolContext
from nyx.tools.close_all_apps import CloseAllApps, CloseAllAppsParams, group_windows, spoken_list
from nyx.winapi import launch, windows
from nyx.winapi.windows import Window

WINDOWS = [
    Window(1, "Inicio - Spotify", "spotify.exe"),
    Window(2, "Descargas", "explorer.exe"),  # el Explorador no se toca
    Window(3, "Google - Chrome", "chrome.exe"),
    Window(4, "Pestaña 2 - Chrome", "chrome.exe"),
    Window(5, "VALORANT", "valorant-win64-shipping.exe"),  # un juego tampoco
    Window(6, "*Sin título - Bloc de notas", "notepad.exe"),
    Window(7, "Algo raro", "raro.exe"),
]


def test_groups_by_app_and_keeps_windows_and_games(ctx: ToolContext) -> None:
    groups = group_windows(WINDOWS, ctx)
    assert [g.label for g in groups] == ["Spotify", "Google Chrome", "Bloc de notas", "Algo raro"]
    assert len(groups[1].windows) == 2  # las dos ventanas de Chrome
    assert groups[3].entry is None  # sin entrada en el índice: el título


def test_spoken_list() -> None:
    assert spoken_list(["Opera"]) == "Opera"
    assert spoken_list(["Opera", "Spotify", "Discord"]) == "Opera, Spotify y Discord"
    many = [f"App {i}" for i in range(9)]
    assert spoken_list(many).endswith("App 5 y 3 más")


async def test_always_red_and_names_what_it_closes(
    ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(windows, "list_windows", lambda: WINDOWS)
    tool = CloseAllApps()
    assert tool.risk is Risk.RED
    prepared = await tool.prepare(CloseAllAppsParams(), ctx)
    assert prepared.error is None
    assert prepared.summary == "Cerrar Spotify, Google Chrome, Bloc de notas y Algo raro"
    assert prepared.detail == "Con cambios sin guardar: Bloc de notas"


async def test_closes_every_window_and_undo_reopens(
    ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed: list[int] = []
    launched: list[str] = []
    monkeypatch.setattr(windows, "list_windows", lambda: WINDOWS)
    monkeypatch.setattr(windows, "close_window", closed.append)
    monkeypatch.setattr(launch, "launch", lambda how: launched.append(how.value))
    tool = CloseAllApps()
    prepared = await tool.prepare(CloseAllAppsParams(), ctx)
    result = await tool.execute(CloseAllAppsParams(), ctx, prepared)
    assert result.ok and closed == [1, 3, 4, 6, 7]
    assert result.undo is not None
    await result.undo.action()
    assert len(launched) == 3  # las que conoce el índice (Algo raro no)


async def test_nothing_open(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(windows, "list_windows", lambda: [WINDOWS[1]])
    prepared = await CloseAllApps().prepare(CloseAllAppsParams(), ctx)
    assert prepared.error is not None
