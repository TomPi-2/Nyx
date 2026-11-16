"""8.08: bloquear por voz y ocultar apps del todo (y que siempre vuelvan)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from nyx.brain.router import Route, route
from nyx.index.service import SystemIndex
from nyx.tools.base import ToolContext
from nyx.tools.hide_apps import HideApps, HideAppsParams
from nyx.winapi.hidden import HiddenWindow, HiddenWindows
from nyx.winapi.windows import Window


class Screen:
    """Ventanas falsas: apunta cuáles se ven."""

    def __init__(self) -> None:
        self.visible: dict[int, bool] = {1: True, 2: True, 3: True}

    def show(self, hwnd: int, show: bool) -> bool:
        if hwnd not in self.visible:
            return False  # ya no existe
        self.visible[hwnd] = show
        return True


def test_hidden_windows_always_come_back(tmp_path: Path) -> None:
    screen = Screen()
    store = HiddenWindows(tmp_path / "ocultas.json", show=screen.show)
    done = store.hide([HiddenWindow(1, "discord.exe", "Discord"), HiddenWindow(9, "x.exe", "X")])
    assert [w.hwnd for w in done] == [1] and not screen.visible[1]
    # Apuntada en disco: otro Nyx (tras un cierre de golpe) la devuelve.
    again = HiddenWindows(tmp_path / "ocultas.json", show=screen.show)
    assert [w.hwnd for w in again.hidden()] == [1]
    assert [w.hwnd for w in again.show()] == [1] and screen.visible[1]
    assert again.hidden() == []


async def test_tool_hides_and_shows(
    ctx: ToolContext, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import nyx.tools.hide_apps as module
    from nyx.winapi import games

    screen = Screen()
    store = HiddenWindows(tmp_path / "ocultas.json", show=screen.show)
    found = [Window(1, "Discord", "discord.exe"), Window(2, "Amigos - Discord", "discord.exe")]
    monkeypatch.setattr(module, "find_target_windows", lambda ctx, name: found)
    monkeypatch.setattr(games, "window_is_game", lambda *a: False)
    tool = HideApps(store)
    hidden = await tool.run(HideAppsParams(action="hide", app="Discord"), ctx)
    assert hidden.ok and not screen.visible[1] and not screen.visible[2]
    assert hidden.undo is not None
    await hidden.undo.action()
    assert screen.visible[1] and screen.visible[2]

    await tool.run(HideAppsParams(action="hide", app="Discord"), ctx)
    monkeypatch.setattr("nyx.tools.focus_window.process_for", lambda ctx, app: "discord.exe")
    shown = await tool.run(HideAppsParams(action="show", app="discord"), ctx)
    assert shown.ok and screen.visible[1]
    nothing = await tool.run(HideAppsParams(action="show"), ctx)
    assert nothing.message == "No tengo nada oculto."

    monkeypatch.setattr(games, "window_is_game", lambda *a: True)
    game = await tool.run(HideAppsParams(action="hide", app="Valorant"), ctx)
    assert not game.ok and "juegos" in game.message
    monkeypatch.setattr(module, "find_target_windows", lambda ctx, name: [])
    missing = await tool.run(HideAppsParams(action="hide", app="Nada"), ctx)
    assert not missing.ok


@pytest.mark.parametrize(
    ("text", "calls"),
    [
        (
            "Apaga el wifi y bloquea",
            [("toggle_wifi", {"enabled": False}), ("system_power", {"action": "lock"})],
        ),
        ("Bloquéalo", [("system_power", {"action": "lock"})]),
        ("Me voy, bloquea", [("system_power", {"action": "lock"})]),
        ("Oculta Discord del todo", [("hide_apps", {"action": "hide", "app": "Discord"})]),
        ("Esconde WhatsApp de la barra", [("hide_apps", {"action": "hide", "app": "WhatsApp"})]),
        ("Oculta Discord", [("window_layout", {"action": "minimize", "name": "discord"})]),
    ],
)
def test_router(index: SystemIndex, text: str, calls: list[tuple[str, dict[str, Any]]]) -> None:
    routed = route(text, index)
    assert isinstance(routed, Route)
    assert [(c.name, c.arguments) for c in routed.calls] == calls


def test_show_only_when_something_is_hidden(
    index: SystemIndex, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(HiddenWindows, "hidden", lambda self: [])
    routed = route("Enséñalo", index)
    assert not (isinstance(routed, Route) and routed.rule == "show_hidden")
    monkeypatch.setattr(
        HiddenWindows, "hidden", lambda self: [HiddenWindow(1, "discord.exe", "Discord")]
    )
    for text, app in (("Enséñalas", None), ("Vuelve a mostrar Discord", "Discord")):
        routed = route(text, index)
        assert isinstance(routed, Route) and routed.rule == "show_hidden"
        assert routed.calls[0].arguments.get("app") == app
