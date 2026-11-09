"""Traer al frente la ventana de lo que se acaba de abrir."""

import pytest

from nyx.winapi import focus, windows
from nyx.winapi.windows import Window

OLD = Window(1, "Sin título: Bloc de notas", "notepad.exe")
NEW = Window(2, "Sin título: Bloc de notas", "notepad.exe")


@pytest.fixture
def screen(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[object]]:
    state: dict[str, list[object]] = {"windows": [OLD], "activated": []}
    monkeypatch.setattr(windows, "list_windows", lambda: list(state["windows"]))  # type: ignore[arg-type]
    monkeypatch.setattr(windows, "activate", lambda h: state["activated"].append(h) or True)
    monkeypatch.setattr(focus, "POLL_S", 0.01)
    return state


async def test_prefers_the_new_window(screen: dict[str, list[object]]) -> None:
    before = focus.snapshot()
    screen["windows"] = [OLD, NEW]
    assert await focus.bring_to_front("Bloc de notas", "notepad.exe", before)
    assert screen["activated"] == [2]


async def test_reuses_existing_window_of_single_instance_app(
    screen: dict[str, list[object]],
) -> None:
    before = focus.snapshot()  # la app ya estaba abierta y no crea ventana nueva
    assert await focus.bring_to_front("Bloc de notas", "notepad.exe", before, reuse_after_s=0.05)
    assert screen["activated"] == [1]


async def test_gives_up_if_nothing_appears(screen: dict[str, list[object]]) -> None:
    assert not await focus.bring_to_front("Spotify", None, focus.snapshot(), timeout_s=0.1)
    assert screen["activated"] == []
