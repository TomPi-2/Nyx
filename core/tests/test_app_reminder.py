"""8.03: recordatorios que saltan al abrir una app (nunca en partida)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from nyx.alarms.scheduler import AlarmScheduler
from nyx.alarms.store import AlarmStore
from nyx.brain.router import Route, route
from nyx.bus import EventBus
from nyx.game.detector import ForegroundChanged, GameStateChanged
from nyx.index.service import SystemIndex
from nyx.organizer.context import AppReminders, matches
from nyx.organizer.store import AppReminder, OrganizerStore
from nyx.tools.app_reminder import AppReminderParams, AppReminderTool
from nyx.tools.base import ToolContext

NOW = datetime(2026, 11, 16, 9, 0).timestamp()


@pytest.fixture
def store(tmp_path: Path) -> OrganizerStore:
    return OrganizerStore(tmp_path / "organizer.db", clock=lambda: NOW)


@pytest.fixture
def alarms(tmp_path: Path) -> AlarmScheduler:
    return AlarmScheduler(AlarmStore(tmp_path / "a.db"), EventBus(), lambda: NOW)


def test_matches() -> None:
    known = AppReminder(1, "Discord", "discord.exe", "x")
    assert matches(known, "Discord.exe", "Amigos")
    assert not matches(known, "steam.exe", "Discord en Steam")  # por su ejecutable
    unknown = AppReminder(2, "Outlook", None, "x")
    assert matches(unknown, "olk.exe", "Bandeja de entrada - Outlook")
    assert not matches(unknown, "chrome.exe", "Google")


async def test_fires_once_and_waits_for_the_game(
    store: OrganizerStore, alarms: AlarmScheduler
) -> None:
    bus = EventBus()
    playing = [False]
    AppReminders(bus, store, alarms, playing=lambda: playing[0])
    store.add_app_reminder("Discord", "discord.exe", "pasarle el enlace a Ana")
    store.add_app_reminder("Steam", "steam.exe", "hay rebajas")
    await bus.publish(ForegroundChanged("chrome.exe", "Google"))
    assert alarms.pending() == []
    await bus.publish(ForegroundChanged("discord.exe", "Discord"))
    (alarm,) = alarms.pending()
    assert alarm.label == "pasarle el enlace a Ana"
    await bus.publish(ForegroundChanged("discord.exe", "Discord"))
    assert len(alarms.pending()) == 1  # una sola vez
    # Jugando, espera a que acabe la partida.
    playing[0] = True
    await bus.publish(ForegroundChanged("steam.exe", "Steam"))
    assert len(alarms.pending()) == 1
    playing[0] = False
    await bus.publish(GameStateChanged(False, "juego.exe"))
    assert [a.label for a in alarms.pending()][-1] == "hay rebajas"
    assert store.app_reminders() == []


async def test_tool(
    ctx: ToolContext, store: OrganizerStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx.organizer = store
    monkeypatch.setattr("nyx.tools.focus_window.process_for", lambda ctx, app: "discord.exe")
    tool = AppReminderTool()
    added = await tool.run(
        AppReminderParams(action="add", app="Discord", text="pasarle el enlace a Ana"), ctx
    )
    assert added.message == "Cuando abras Discord, te recuerdo: pasarle el enlace a Ana."
    assert store.app_reminders()[0].process == "discord.exe"
    listed = await tool.run(AppReminderParams(action="list"), ctx)
    assert listed.message == "Tienes: al abrir Discord, pasarle el enlace a Ana."
    gone = await tool.run(AppReminderParams(action="delete", app="discord"), ctx)
    assert gone.ok and store.app_reminders() == []
    assert gone.undo is not None
    await gone.undo.action()
    assert len(store.app_reminders()) == 1


@pytest.mark.parametrize(
    ("text", "app", "what"),
    [
        (
            "Cuando abra Discord, recuérdame que le pase el enlace a Ana",
            "Discord",
            "le pase el enlace a Ana",
        ),
        ("La próxima vez que entre en Steam avísame de que hay rebajas", "Steam", "hay rebajas"),
        ("Recuérdame mirar el correo cuando abra Outlook", "Outlook", "mirar el correo"),
    ],
)
def test_router(index: SystemIndex, text: str, app: str, what: str) -> None:
    routed = route(text, index)
    assert isinstance(routed, Route) and routed.rule == "app_reminder"
    assert routed.calls[0].arguments == {"action": "add", "app": app, "text": what}


def test_router_no_places(index: SystemIndex) -> None:
    routed = route("Cuando llegue a casa recuérdame sacar la basura", index)
    assert not (isinstance(routed, Route) and routed.rule == "app_reminder")
