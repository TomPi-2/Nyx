"""Confirmaciones (botones y voz) y deshacer en el bucle de voz (bloque 3b)."""

import asyncio
from typing import ClassVar

import numpy as np
import pytest

from nyx import pipeline as pipeline_module
from nyx.brain.router import Route
from nyx.events import ActionChosen, NyxState, TextEntered
from nyx.executor import Executor, ToolCall
from nyx.pipeline import Mode
from nyx.safety.undo import Undo
from nyx.tools.base import (
    Category,
    GamePolicy,
    Params,
    Prepared,
    Risk,
    Tool,
    ToolContext,
    ToolResult,
)
from nyx.tools.registry import ToolRegistry
from nyx.tools.undo import UndoLast
from tests.test_pipeline import Harness

YES_FRAME, NO_FRAME = 11, 12


class Nothing(Params):
    pass


class Danger(Tool[Nothing]):
    name = "danger"
    description = "roja"
    risk = Risk.RED
    game_policy = GamePolicy.BLOCKED
    category = Category.FILES
    params_model = Nothing
    done: ClassVar[list[str]] = []
    click_only: ClassVar[bool] = False

    async def prepare(self, params: Nothing, ctx: ToolContext) -> Prepared:
        count = 60 if type(self).click_only else 1
        return Prepared("Mandar a la papelera «a.txt»", detail="de Descargas", count=count)

    async def execute(self, params: Nothing, ctx: ToolContext, prepared: Prepared) -> ToolResult:
        type(self).done.append("borrado")
        return ToolResult(ok=True, message="En la papelera")


class Mover(Tool[Nothing]):
    name = "mover"
    description = "amarilla"
    risk = Risk.YELLOW
    game_policy = GamePolicy.DEFERRED
    category = Category.FILES
    params_model = Nothing
    undone: ClassVar[list[str]] = []

    async def run(self, params: Nothing, ctx: ToolContext) -> ToolResult:
        async def undo() -> str:
            type(self).undone.append("deshecho")
            return "Devueltos a Descargas"

        return ToolResult(
            ok=True, message="Movidos", display="Movidos a Documentos", undo=Undo("Mover", undo)
        )


class FakeYesNo:
    def process(self, frame: np.ndarray) -> bool | None:
        value = int(frame[0])
        return True if value == YES_FRAME else False if value == NO_FRAME else None

    def reset(self) -> None:
        pass


def setup(h: Harness, ctx: ToolContext, tool: str) -> Executor:
    Danger.done, Mover.undone = [], []
    ex = Executor(ToolRegistry([Danger(), Mover(), UndoLast()]), ctx)
    h.p.executor = ex
    ex.confirm = h.p.confirm
    h.p.yesno = FakeYesNo()
    h.p.router = lambda text: Route([ToolCall(tool)], tool)
    return ex


async def wait_for_buttons(h: Harness) -> list[str]:
    for _ in range(200):
        await asyncio.sleep(0)
        if h.p._actions:
            return list(h.p._actions)
    raise AssertionError("no aparecen los botones")


async def test_red_action_confirmed_with_button(ctx: ToolContext) -> None:
    h = Harness()
    setup(h, ctx, "danger")
    await h.bus.publish(TextEntered("borra a.txt"))
    yes, _no = await wait_for_buttons(h)
    assert h.p.state is NyxState.CONFIRM
    assert h.bubbles[-1] == ("Mandar a la papelera «a.txt»", "de Descargas · di «sí» o «no»")
    await h.bus.publish(ActionChosen(yes))
    await h.p.wait_idle()
    assert Danger.done == ["borrado"]
    await h.p.close()


async def test_red_action_cancelled_with_button(ctx: ToolContext) -> None:
    h = Harness()
    setup(h, ctx, "danger")
    await h.bus.publish(TextEntered("borra a.txt"))
    _yes, no = await wait_for_buttons(h)
    await h.bus.publish(ActionChosen(no))
    await h.p.wait_idle()
    assert Danger.done == []
    assert h.bubbles[-1][0] == "Cancelado"
    assert NyxState.ERROR not in h.states  # cancelar no es un error
    await h.p.close()


async def test_red_action_confirmed_by_voice(ctx: ToolContext) -> None:
    h = Harness()
    setup(h, ctx, "danger")
    await h.say()  # «Nix, borra…» (el router falso devuelve la acción roja)
    await wait_for_buttons(h)
    for _ in range(50):
        await asyncio.sleep(0)
        if h.p.mode is Mode.CONFIRM:
            break
    assert h.p.mode is Mode.CONFIRM
    assert h.tts.said[-1] == "Mandar a la papelera «a.txt». ¿Confirmas?"
    await h.feed(YES_FRAME)
    await h.p.wait_idle()
    assert Danger.done == ["borrado"]
    await h.p.close()


async def test_click_only_ignores_voice(ctx: ToolContext) -> None:
    h = Harness()
    setup(h, ctx, "danger")
    Danger.click_only = True
    try:
        await h.bus.publish(TextEntered("borra todo"))
        yes, _ = await wait_for_buttons(h)
        assert h.p.mode is not Mode.CONFIRM  # la voz no cuenta
        assert "solo con clic" not in h.bubbles[-1][1]  # sin pista de voz
        await h.feed(YES_FRAME)
        assert Danger.done == []
        await h.bus.publish(ActionChosen(yes))
        await h.p.wait_idle()
        assert Danger.done == ["borrado"]
    finally:
        Danger.click_only = False
    await h.p.close()


async def test_confirmation_expires(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline_module, "CONFIRM_TIMEOUT_S", 0.05)
    h = Harness()
    setup(h, ctx, "danger")
    await h.bus.publish(TextEntered("borra a.txt"))
    await h.p.wait_idle()
    assert Danger.done == []
    assert h.bubbles[-1][0] == "Cancelado"
    await h.p.close()


async def test_yellow_action_offers_undo_button(ctx: ToolContext) -> None:
    h = Harness()
    setup(h, ctx, "mover")
    await h.bus.publish(TextEntered("mueve…"))
    await h.p.wait_idle()
    assert h.bubbles[-1] == ("Movidos a Documentos", None)
    (button,) = list(h.p._actions)
    await h.bus.publish(ActionChosen(button))
    for _ in range(100):
        await asyncio.sleep(0)
        if Mover.undone:
            break
    assert Mover.undone == ["deshecho"]
    for _ in range(100):
        await asyncio.sleep(0)
        if h.bubbles[-1][0] == "Deshecho":
            break
    assert h.bubbles[-1] == ("Deshecho", "Devueltos a Descargas")
    await h.bus.publish(ActionChosen(button))  # el botón ya no hace nada
    assert Mover.undone == ["deshecho"]
    await h.p.close()
