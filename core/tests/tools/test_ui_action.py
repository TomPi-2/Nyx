"""ui_action (6.14): pulsar, marcar o leer por nombre; rojo en lo que no tiene vuelta atrás."""

from __future__ import annotations

from typing import Any

import pytest

from nyx.tools.base import GamePolicy, Risk, ToolContext
from nyx.tools.ui_action import Control, Found, UiAction, UiActionParams, _match
from nyx.winapi.windows import Window


class FakeUia:
    def __init__(self, names: list[tuple[str, str]], text: str = "") -> None:
        self.names = names
        self.text = text
        self.acted: list[tuple[str, str]] = []

    def __call__(
        self, hwnd: int, wanted: str, action: str, expect: Control | None
    ) -> tuple[Found, str]:
        found = _match(self.names, wanted)
        if expect is not None and found.control == expect:  # como el real: solo si es ese
            self.acted.append((action, found.control.name))
            return found, self.text
        return found, ""


@pytest.fixture
def window(monkeypatch: pytest.MonkeyPatch) -> Window:
    win = Window(hwnd=42, title="Ajustes de la app", process="app.exe")
    monkeypatch.setattr("nyx.winapi.windows.foreground", lambda: win)
    monkeypatch.setattr("nyx.winapi.games.window_is_game", lambda *a: False)
    return win


def test_metadata() -> None:
    assert UiAction.risk is Risk.YELLOW
    assert UiAction.game_policy is GamePolicy.BLOCKED


def test_match_never_guesses() -> None:
    names = [("Aceptar", "botón"), ("Cancelar", "botón"), ("Guardar cambios", "botón"),
             ("Guardar como", "botón")]  # fmt: skip
    assert _match(names, "aceptar").control == Control("Aceptar", "botón")
    assert _match(names, "Guardar").options == ("Guardar cambios", "Guardar como")
    assert _match(names, "Imprimir") == Found()


async def test_click_is_yellow_and_acts_on_the_confirmed_control(
    ctx: ToolContext, window: Window
) -> None:
    uia = FakeUia([("Aceptar", "botón")])
    tool = UiAction(backend=uia)
    params = UiActionParams(action="click", control="aceptar")
    prepared = await tool.prepare(params, ctx)
    assert prepared.error is None and prepared.risk is Risk.YELLOW
    assert prepared.summary == "Pulsar el botón «Aceptar» en Ajustes de la app"
    result = await tool.execute(params, ctx, prepared)
    assert result.ok and uia.acted == [("click", "Aceptar")]
    assert result.secondary == "no se puede deshacer"


@pytest.mark.parametrize("name", ["Eliminar cuenta", "Enviar", "Pagar ahora", "Desinstalar"])
async def test_irreversible_controls_are_red(ctx: ToolContext, window: Window, name: str) -> None:
    tool = UiAction(backend=FakeUia([(name, "botón")]))
    prepared = await tool.prepare(UiActionParams(action="click", control=name), ctx)
    assert prepared.risk is Risk.RED


async def test_read_is_green_and_external(ctx: ToolContext, window: Window) -> None:
    tool = UiAction(backend=FakeUia([("Aviso", "texto")], text="Tu sesión caduca hoy"))
    params = UiActionParams(action="read", control="Aviso")
    prepared = await tool.prepare(params, ctx)
    assert prepared.risk is Risk.GREEN
    result = await tool.execute(params, ctx, prepared)
    assert result.external == "Tu sesión caduca hoy" and "caduca" not in result.message


async def test_window_changed_does_nothing(ctx: ToolContext, window: Window) -> None:
    uia = FakeUia([("Aceptar", "botón")])
    tool = UiAction(backend=uia)
    params = UiActionParams(action="click", control="Aceptar")
    prepared = await tool.prepare(params, ctx)
    uia.names = [("Aceptar", "enlace")]  # ya no es el mismo control
    result = await tool.execute(params, ctx, prepared)
    assert not result.ok and uia.acted == []  # comprobado ANTES de tocar nada


async def test_refuses_games_nyx_and_ambiguity(
    ctx: ToolContext, window: Window, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = UiAction(backend=FakeUia([("Guardar cambios", "botón"), ("Guardar como", "botón")]))
    prepared = await tool.prepare(UiActionParams(action="click", control="Guardar"), ctx)
    assert prepared.error is not None and "varios" in prepared.error.message

    monkeypatch.setattr("nyx.winapi.games.window_is_game", lambda *a: True)
    prepared = await tool.prepare(UiActionParams(action="click", control="Guardar"), ctx)
    assert prepared.error is not None and "juegos" in prepared.error.message

    nyx: Any = Window(hwnd=1, title="Nyx", process="nyx-ui.exe")
    monkeypatch.setattr("nyx.winapi.windows.foreground", lambda: nyx)
    prepared = await tool.prepare(UiActionParams(action="read", control="x"), ctx)
    assert prepared.error is not None
