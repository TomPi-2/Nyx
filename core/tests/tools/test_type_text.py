from __future__ import annotations

import pytest

from nyx.executor import Confirmation, Executor, ToolCall
from nyx.tools import type_text as type_text_module
from nyx.tools.base import Category, GamePolicy, Risk, ToolContext
from nyx.tools.registry import default_registry
from nyx.tools.type_text import TypeText
from nyx.winapi import games, keys, windows
from nyx.winapi.windows import Window
from tests.tools.fakes import FakeDesktop

NOTEPAD = Window(5, "Sin título: Bloc de notas", "notepad.exe")
TERMINAL = Window(7, "Windows PowerShell", "windowsterminal.exe")
NYX = Window(9, "Nyx", "nyx-ui.exe")
GAME = Window(12, "VALORANT", "VALORANT-Win64-Shipping.exe")


def test_metadata() -> None:
    tool = TypeText()
    assert tool.name == "type_text"
    assert tool.risk is Risk.YELLOW
    assert tool.game_policy is GamePolicy.BLOCKED
    assert tool.category is Category.WINDOWS
    assert tool.observe is False


def test_encode_unicode_events_handles_spanish_and_newlines() -> None:
    events = keys.encode_unicode_events("ñ\n")
    assert events == [
        (0, ord("ñ"), keys.KEYEVENTF_UNICODE),
        (0, ord("ñ"), keys.KEYEVENTF_UNICODE | keys.KEYEVENTF_KEYUP),
        (keys.VK_RETURN, 0, 0),
        (keys.VK_RETURN, 0, keys.KEYEVENTF_KEYUP),
    ]


@pytest.fixture
def typed(monkeypatch: pytest.MonkeyPatch) -> tuple[list[str], list[str]]:
    written: list[str] = []
    pressed: list[str] = []
    monkeypatch.setattr(keys, "write", lambda t: written.append(t) or True)
    monkeypatch.setattr(keys, "press", lambda hk: pressed.append(hk.label))
    monkeypatch.setattr(type_text_module, "FOCUS_SETTLE_S", 0.0)
    monkeypatch.setattr(games, "window_is_game", lambda hwnd, proc, known: hwnd == GAME.hwnd)
    return written, pressed


async def test_type_text_writes_and_supports_undo(
    ctx: ToolContext, desktop: FakeDesktop, typed: tuple[list[str], list[str]]
) -> None:
    written, pressed = typed
    desktop.windows, desktop.fg = [NYX, NOTEPAD], 9
    ex = Executor(default_registry(), ctx)
    res = await ex.run(
        ToolCall("type_text", {"text": "llego en 10 minutos", "app": "bloc de notas"})
    )
    assert res.ok
    assert written == ["llego en 10 minutos"]
    assert desktop.activated == [NOTEPAD.hwnd]
    assert res.data.get("undo_id")

    undo_res = await ex.run(ToolCall("undo"))
    assert undo_res.ok
    assert pressed == ["Ctrl+Z"]


async def test_type_text_blocks_nyx_games_and_over_limit(
    ctx: ToolContext, desktop: FakeDesktop, typed: tuple[list[str], list[str]]
) -> None:
    written, _ = typed
    ex = Executor(default_registry(), ctx)

    # Ventana de Nyx activa → rechazado
    desktop.windows, desktop.fg = [NYX], NYX.hwnd
    assert not (await ex.run(ToolCall("type_text", {"text": "hola"}))).ok

    # Ventana de un juego activa → rechazado
    desktop.windows, desktop.fg = [GAME], GAME.hwnd
    res_game = await ex.run(ToolCall("type_text", {"text": "hola"}))
    assert not res_game.ok
    assert "juegos" in res_game.message

    # Más de 2.000 caracteres → rechazado por validación
    desktop.windows, desktop.fg = [NOTEPAD], NOTEPAD.hwnd
    too_long = await ex.run(ToolCall("type_text", {"text": "x" * 2001}))
    assert not too_long.ok
    assert written == []


def test_control_characters_are_never_typed() -> None:
    # Retroceso, escape o Ctrl+V llegarían a la app como teclas, no como texto.
    events = keys.encode_unicode_events("a\x08\x1b\x16b")
    assert [scan for _, scan, flags in events if not flags & keys.KEYEVENTF_KEYUP] == [
        ord("a"),
        ord("b"),
    ]
    assert keys.presses_keys("hola\nmundo") and keys.presses_keys("a\tb")
    assert not keys.presses_keys("hola mundo")


@pytest.mark.parametrize(
    ("window", "text", "summary"),
    [
        # Intro envía el mensaje o ejecuta la orden: se confirma antes.
        (NOTEPAD, "hola\nmundo", "y pulsar Intro"),
        (NOTEPAD, "nombre\tapellido", "Escribir en"),
        # En una terminal lo escrito es una orden (run_powershell es siempre roja).
        (TERMINAL, "Remove-Item C:\\datos", "la terminal"),
    ],
)
async def test_enter_tab_and_terminals_need_confirmation(
    ctx: ToolContext,
    desktop: FakeDesktop,
    typed: tuple[list[str], list[str]],
    window: Window,
    text: str,
    summary: str,
) -> None:
    written, _ = typed
    desktop.windows, desktop.fg = [window], window.hwnd
    asked: list[Confirmation] = []

    async def deny(c: Confirmation) -> bool:
        asked.append(c)
        return False

    res = await Executor(default_registry(), ctx, confirm=deny).run(
        ToolCall("type_text", {"text": text})
    )
    assert not res.ok and written == []
    assert len(asked) == 1 and summary in asked[0].summary

    async def accept(c: Confirmation) -> bool:
        return True

    res = await Executor(default_registry(), ctx, confirm=accept).run(
        ToolCall("type_text", {"text": text})
    )
    assert res.ok and written == [text]


async def test_undo_never_presses_keys_in_another_window(
    ctx: ToolContext,
    desktop: FakeDesktop,
    typed: tuple[list[str], list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, pressed = typed
    desktop.windows, desktop.fg = [NOTEPAD, GAME], NOTEPAD.hwnd
    ex = Executor(default_registry(), ctx)
    assert (await ex.run(ToolCall("type_text", {"text": "hola"}))).ok
    # El usuario se ha ido a otra ventana (un juego) y Windows no deja volver a la de antes.
    desktop.fg = GAME.hwnd
    monkeypatch.setattr(windows, "activate", lambda hwnd: False)
    undone = await ex.run(ToolCall("undo"))
    assert not undone.ok and pressed == []


async def test_reports_when_windows_refuses_the_input(
    ctx: ToolContext,
    desktop: FakeDesktop,
    typed: tuple[list[str], list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    desktop.windows, desktop.fg = [NOTEPAD], NOTEPAD.hwnd
    monkeypatch.setattr(keys, "write", lambda t: False)
    res = await Executor(default_registry(), ctx).run(ToolCall("type_text", {"text": "hola"}))
    assert not res.ok and "undo_id" not in res.data
