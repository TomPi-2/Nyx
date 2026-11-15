"""8.01: listas y tareas de Nyx (locales, con deshacer y sin borrar nada del todo)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from nyx.alarms.scheduler import AlarmScheduler
from nyx.alarms.store import AlarmStore
from nyx.bus import EventBus
from nyx.organizer.store import OrganizerStore, list_key, split_items
from nyx.settings.model import Settings
from nyx.tools.base import ToolContext
from nyx.tools.list_items import ListItems, ListItemsParams
from nyx.tools.task import TaskParams, TaskTool

NOW = datetime(2026, 11, 16, 9, 0).timestamp()  # lunes, 9:00


@pytest.fixture
def store(tmp_path: Path) -> OrganizerStore:
    return OrganizerStore(tmp_path / "organizer.db", clock=lambda: NOW)


@pytest.fixture
def octx(ctx: ToolContext, store: OrganizerStore, tmp_path: Path) -> ToolContext:
    ctx.organizer = store
    ctx.alarms = AlarmScheduler(AlarmStore(tmp_path / "a.db"), EventBus(), lambda: NOW)
    return ctx


@pytest.mark.parametrize(
    ("said", "key"),
    [
        ("la lista de la compra", "compra"),
        ("mi lista de pendientes", "pendientes"),
        ("lista compra", "compra"),
        ("La Compra", "compra"),
        ("", "pendientes"),
        ("lista de regalos de navidad", "regalos de navidad"),
    ],
)
def test_lists_are_named_as_people_say_them(said: str, key: str) -> None:
    assert list_key(said) == key


def test_split_items() -> None:
    assert split_items("leche, huevos y pan") == ["leche", "huevos", "pan"]
    assert split_items("agua e hielo; Leche, leche") == ["agua", "hielo", "Leche"]
    assert split_items("pan y mantequilla") == ["pan", "mantequilla"]


def test_store_never_deletes_for_good(store: OrganizerStore) -> None:
    added, already = store.add_items("la compra", ["leche", "pan"])
    assert len(added) == 2 and already == []
    assert store.add_items("compra", ["Leche"]) == ([], ["Leche"])
    removed = store.clear("compra")
    assert store.items("compra") == []
    store.restore(removed)
    assert [i.text for i in store.items("compra")] == ["leche", "pan"]


async def test_list_tool_add_read_remove_and_undo(octx: ToolContext) -> None:
    tool = ListItems()
    added = await tool.run(
        ListItemsParams(action="add", list="la compra", items="leche, huevos y pan"), octx
    )
    assert added.ok and added.message == "Apuntado en la lista «compra»: leche, huevos y pan."
    read = await tool.run(ListItemsParams(action="read", list="compra"), octx)
    assert read.speak and read.message == "En la lista «compra»: leche, huevos y pan."
    gone = await tool.run(ListItemsParams(action="remove", list="compra", items="huevos"), octx)
    assert gone.message == "Quitado de la lista «compra»: huevos."
    assert gone.undo is not None
    await gone.undo.action()
    cleared = await tool.run(ListItemsParams(action="clear", list="compra"), octx)
    assert cleared.message == "He vaciado la lista «compra» (3)."
    assert cleared.undo is not None
    await cleared.undo.action()
    lists = await tool.run(ListItemsParams(action="lists"), octx)
    assert lists.message == "Tienes estas listas: «compra» (3)."


async def test_list_tool_does_not_guess(octx: ToolContext) -> None:
    tool = ListItems()
    await tool.run(ListItemsParams(action="add", items="pan de molde y pan rallado"), octx)
    which = await tool.run(ListItemsParams(action="remove", items="pan"), octx)
    assert not which.ok and "¿Cuál?" in which.message
    missing = await tool.run(ListItemsParams(action="done", items="queso"), octx)
    assert not missing.ok and "No encuentro" in missing.message
    done = await tool.run(ListItemsParams(action="done", items="pan rallado"), octx)
    assert done.ok
    read = await tool.run(ListItemsParams(action="read"), octx)
    assert "pan rallado (hecho)" in read.message


async def test_task_with_time_sets_a_reminder(octx: ToolContext) -> None:
    tool = TaskTool()
    added = await tool.run(
        TaskParams(action="add", text="llamar al banco", day="tomorrow", time="10:00"), octx
    )
    assert added.ok and added.message == "Tarea apuntada: llamar al banco (mañana a las 10:00)."
    assert octx.alarms is not None
    (alarm,) = octx.alarms.pending()
    assert alarm.label == "llamar al banco"
    read = await tool.run(TaskParams(action="read", day="tomorrow"), octx)
    assert read.message == "Tienes 1 tarea: llamar al banco (mañana a las 10:00)."
    assert (await tool.run(TaskParams(action="read", day="today"), octx)).message == (
        "No tienes tareas pendientes para ese día."
    )
    done = await tool.run(TaskParams(action="done", text="banco"), octx)
    assert done.message == "Tarea hecha: llamar al banco."
    assert octx.alarms.pending() == []  # el aviso ya no hace falta
    assert done.undo is not None
    await done.undo.action()  # vuelve, con su aviso
    assert len(octx.alarms.pending()) == 1


async def test_task_without_date_and_past_hour(octx: ToolContext) -> None:
    tool = TaskTool()
    plain = await tool.run(TaskParams(action="add", text="renovar el DNI"), octx)
    assert plain.message == "Tarea apuntada: renovar el DNI."
    late = await tool.run(TaskParams(action="add", text="desayunar", time="08:00"), octx)
    assert not late.ok and "ya ha pasado" in late.message
    deleted = await tool.run(TaskParams(action="delete", text="dni"), octx)
    assert deleted.ok and deleted.undo is not None
    assert (await tool.run(TaskParams(action="read"), octx)).message == (
        "No tienes tareas pendientes."
    )


async def test_without_store(ctx: ToolContext) -> None:
    result = await ListItems().run(ListItemsParams(action="read"), ctx)
    assert not result.ok
    assert Settings() is not None


async def test_tick_without_saying_the_list(octx: ToolContext) -> None:
    tool = ListItems()
    await tool.run(ListItemsParams(action="add", list="la compra", items="los huevos"), octx)
    done = await tool.run(ListItemsParams(action="done", items="los huevos"), octx)
    assert done.ok and done.message == "Tachado en la lista «compra»: huevos."
