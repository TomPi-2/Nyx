"""8.04: dictado (escribir lo que se dice hasta «ya está»)."""

from __future__ import annotations

from typing import Any

import pytest

from nyx.brain.router import Route, route
from nyx.dictation import Dictation, is_stop, spoken_text
from nyx.index.service import SystemIndex
from nyx.pipeline import Mode
from nyx.tools.base import ToolContext
from nyx.tools.dictation_tool import DictationParams, DictationTool
from nyx.winapi.windows import Window
from tests.test_pipeline import SILENCE, SPEECH, FakeSTT, Harness, n


class Keyboard:
    def __init__(self) -> None:
        self.out: list[str] = []
        self.focus_ok = True

    def write(self, text: str) -> bool:
        self.out.append(text)
        return True

    def new_line(self) -> None:
        self.out.append("⏎")

    def focus(self, hwnd: int) -> bool:
        return self.focus_ok


def make(keyboard: Keyboard) -> Dictation:
    return Dictation(write=keyboard.write, new_line=keyboard.new_line, focus=keyboard.focus)


@pytest.mark.parametrize(
    ("said", "typed"),
    [
        ("Hola coma qué tal punto", "Hola, qué tal."),
        ("Nyx, querida Ana dos puntos nueva línea te escribo", "querida Ana:\nTe escribo"),
        ("abre interrogación vienes mañana cierra interrogación", "¿vienes mañana?"),
        ("la puntuación importa", "la puntuación importa"),
    ],
)
def test_spoken_punctuation(said: str, typed: str) -> None:
    assert spoken_text(said) == typed


def test_stop_phrases() -> None:
    assert is_stop("Ya está.") and is_stop("Nyx, fin del dictado") and is_stop("para de escribir")
    assert not is_stop("ya vienen")


def test_never_presses_a_bare_enter() -> None:
    keyboard = Keyboard()
    d = make(keyboard)
    d.start(7, "Bloc de notas")
    assert d.type("primera línea nueva línea segunda")
    assert d.type("y más")
    assert keyboard.out == ["primera línea", "⏎", "Segunda", " y más"]
    keyboard.focus_ok = False  # la ventana ya no está
    assert not d.type("otra")


async def test_pipeline_dictates_until_ya_esta() -> None:
    stt = FakeSTT()
    stt.script = ["Hola coma qué tal punto", "Ya está."]
    h = Harness(stt=stt)
    keyboard = Keyboard()
    h.p.dictation = make(keyboard)
    h.p.dictation.start(7, "Bloc de notas")
    await h.p._go_idle()  # tras decir «te escucho», escucha sin «Nyx»
    assert h.p.mode is Mode.LISTENING
    await h.feed(SILENCE, n(0.4))
    await h.feed(SPEECH, n(1.0))
    await h.feed(SILENCE, n(0.8))
    await h.p.wait_idle()
    assert keyboard.out == ["Hola, qué tal."]
    assert h.p.mode is Mode.LISTENING  # sigue escuchando
    await h.feed(SILENCE, n(0.4))
    await h.feed(SPEECH, n(0.5))
    await h.feed(SILENCE, n(0.8))
    await h.p.wait_idle()
    assert not h.p.dictation.active and h.p.mode is Mode.IDLE
    assert ("Dictado terminado", None) in h.bubbles
    assert h.llm.asked == []  # nada fue al cerebro
    await h.p.close()


async def test_pipeline_dictation_ends_after_silence() -> None:
    h = Harness()
    h.p.dictation = make(Keyboard())
    h.p.dictation.start(7, "Bloc de notas")
    await h.p._go_idle()
    await h.feed(SILENCE, n(21.0))
    assert not h.p.dictation.active and h.p.mode is Mode.IDLE
    await h.p.close()


async def test_tool(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    from nyx.winapi import games, windows

    shown = [Window(1, "Nyx", "nyx-ui.exe"), Window(2, "Sin título - Bloc de notas", "notepad.exe")]
    monkeypatch.setattr(windows, "list_windows", lambda: shown)
    monkeypatch.setattr(games, "window_is_game", lambda *a: False)
    ctx.dictation = make(Keyboard())
    tool = DictationTool()
    started = await tool.run(DictationParams(), ctx)
    assert started.ok and ctx.dictation.target.hwnd == 2  # no Nyx
    stopped = await tool.run(DictationParams(action="stop"), ctx)
    assert stopped.ok and not ctx.dictation.active
    shown[1] = Window(3, "PowerShell", "windowsterminal.exe")
    terminal = await tool.run(DictationParams(), ctx)
    assert not terminal.ok and "terminal" in terminal.message


@pytest.mark.parametrize(
    ("text", "args"),
    [
        ("Escribe lo que te diga", {"action": "start"}),
        ("Empieza el dictado en Word", {"action": "start", "app": "Word"}),
        ("Termina el dictado", {"action": "stop"}),
    ],
)
def test_router(index: SystemIndex, text: str, args: dict[str, Any]) -> None:
    routed = route(text, index)
    assert isinstance(routed, Route) and routed.calls[0].arguments == args


async def test_short_followup_window_does_not_end_dictation() -> None:
    h = Harness()  # ventana de seguimiento de 1 s
    h.p.dictation = make(Keyboard())
    h.p.dictation.start(7, "Bloc de notas")
    await h.p.start_listening(followup=True)  # como tras decir «te escucho»
    await h.feed(SILENCE, n(5.0))
    assert h.p.dictation.active and h.p.mode is Mode.LISTENING
    await h.feed(SILENCE, n(17.0))
    assert not h.p.dictation.active
    await h.p.close()
