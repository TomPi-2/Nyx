import pytest

from nyx.executor import Executor, ToolCall
from nyx.tools import send_hotkey as hotkey_module
from nyx.tools.base import ToolContext
from nyx.tools.registry import default_registry
from nyx.winapi import keys
from nyx.winapi.windows import Window
from tests.tools.fakes import FakeDesktop

NOTEPAD = Window(5, "Sin título: Bloc de notas", "notepad.exe")
NYX = Window(9, "Nyx", "nyx-ui.exe")


@pytest.mark.parametrize(
    ("text", "names", "codes"),
    [
        ("ctrl+t", ("ctrl", "t"), (0x11, 0x54)),
        ("Ctrl + Shift + N", ("ctrl", "shift", "n"), (0x11, 0x10, 0x4E)),
        ("F11", ("f11",), (0x7A,)),
        ("alt+tab", ("alt", "tab"), (0x12, 0x09)),
        ("ctrl++", ("ctrl", "+"), (0x11, 0xBB)),
    ],
)
def test_parse(text: str, names: tuple[str, ...], codes: tuple[int, ...]) -> None:
    hk = keys.parse(text)
    assert hk.names == names and hk.codes == codes


@pytest.mark.parametrize("text", ["ctrl+", "hiper+t", "ctrl+ñ", ""])
def test_parse_rejects(text: str) -> None:
    with pytest.raises(ValueError):
        keys.parse(text)


@pytest.mark.parametrize("text", ["alt+f4", "shift+supr", "win+r", "Ctrl+Alt+Delete", "supr"])
def test_dangerous_hotkeys_are_blocked(text: str) -> None:
    assert keys.blocked_reason(keys.parse(text))


@pytest.fixture
def pressed(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []
    monkeypatch.setattr(keys, "press", lambda hk: seen.append(hk.label))
    monkeypatch.setattr(hotkey_module, "FOCUS_SETTLE_S", 0.0)
    return seen


async def test_hotkey_in_named_app_focuses_it_first(
    ctx: ToolContext, desktop: FakeDesktop, pressed: list[str]
) -> None:
    desktop.windows, desktop.fg = [NYX, NOTEPAD], 9
    ex = Executor(default_registry(), ctx)
    result = await ex.run(ToolCall("send_hotkey", {"keys": "ctrl+t", "app": "bloc de notas"}))
    assert result.ok and pressed == ["Ctrl+T"]
    assert desktop.activated == [5]


async def test_hotkey_never_goes_to_nyx_or_blocked(
    ctx: ToolContext, desktop: FakeDesktop, pressed: list[str]
) -> None:
    desktop.windows, desktop.fg = [NYX], 9
    ex = Executor(default_registry(), ctx)
    assert not (await ex.run(ToolCall("send_hotkey", {"keys": "ctrl+t"}))).ok
    blocked = await ex.run(ToolCall("send_hotkey", {"keys": "alt+f4", "app": "bloc de notas"}))
    assert not blocked.ok
    assert pressed == []
