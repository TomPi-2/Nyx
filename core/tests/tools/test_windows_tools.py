from nyx.tools.base import ToolContext
from nyx.tools.focus_window import FocusWindow, FocusWindowParams
from nyx.tools.wait_for_window import WaitForWindow, WaitForWindowParams
from nyx.tools.window_layout import WindowLayout, WindowLayoutParams
from nyx.winapi import windows
from nyx.winapi.windows import Window
from tests.tools.fakes import FakeDesktop

CHROME = Window(1, "Nueva pestaña - Google Chrome", "chrome.exe")
CODE = Window(2, "SPEC.md - Nyx - Visual Studio Code", "code.exe")
DISCORD = Window(3, "@Txiki - Discord", "discordptb.exe")


def test_find_windows_by_process_and_title() -> None:
    ws = [CHROME, CODE, DISCORD]
    assert windows.find_windows("vscode", "code.exe", ws) == [CODE]
    assert windows.find_windows("discord", None, ws) == [DISCORD]
    assert windows.find_windows("chrome", None, ws) == [CHROME]
    assert windows.find_windows("spotify", None, ws) == []


def test_geometry() -> None:
    assert windows.half((0, 0, 2560, 1400), "left") == (0, 0, 1280, 1400)
    assert windows.half((0, 0, 2560, 1400), "right") == (1280, 0, 2560, 1400)
    # Ventana a mitad del monitor de 2560×1400 → mismo sitio relativo en el de 1920×1040.
    moved = windows.translate((0, 0, 1280, 700), (0, 0, 2560, 1400), (2560, 0, 4480, 1040))
    assert moved == (2560, 0, 3520, 520)
    screens = FakeDesktop().screens
    assert windows.monitor_of((3000, 100, 3500, 500), screens) == 1
    assert windows.monitor_of((-5000, 0, -4000, 10), screens) == 0


async def test_focus(ctx: ToolContext, desktop: FakeDesktop) -> None:
    desktop.windows = [CHROME, CODE]
    result = await FocusWindow().run(FocusWindowParams(name="visual studio code"), ctx)
    assert result.ok
    assert desktop.activated == [2]


async def test_focus_not_open(ctx: ToolContext, desktop: FakeDesktop) -> None:
    result = await FocusWindow().run(FocusWindowParams(name="spotify"), ctx)
    assert not result.ok and desktop.activated == []


async def test_layout_maximize_active_window(ctx: ToolContext, desktop: FakeDesktop) -> None:
    desktop.windows, desktop.fg = [CHROME], 1
    result = await WindowLayout().run(WindowLayoutParams(action="maximize"), ctx)
    assert result.ok
    assert desktop.shown == [(1, "maximize")]


async def test_layout_left_half(ctx: ToolContext, desktop: FakeDesktop) -> None:
    desktop.windows, desktop.rects = [DISCORD], {3: (100, 100, 900, 700)}
    result = await WindowLayout().run(WindowLayoutParams(action="left", name="discord"), ctx)
    assert result.ok
    assert desktop.placed == [(3, (0, 0, 1280, 1400))]


async def test_layout_next_monitor_keeps_maximized(ctx: ToolContext, desktop: FakeDesktop) -> None:
    desktop.windows, desktop.fg = [CHROME], 1
    desktop.rects, desktop.maximized = {1: (0, 0, 1280, 700)}, {1}
    result = await WindowLayout().run(WindowLayoutParams(action="next_monitor"), ctx)
    assert result.ok
    assert desktop.placed[0][1][0] >= 2560  # en el segundo monitor
    assert desktop.shown == [(1, "restore"), (1, "maximize")]


async def test_layout_next_monitor_single_screen(ctx: ToolContext, desktop: FakeDesktop) -> None:
    desktop.windows, desktop.fg, desktop.rects = [CHROME], 1, {1: (0, 0, 10, 10)}
    desktop.screens = desktop.screens[:1]
    result = await WindowLayout().run(WindowLayoutParams(action="next_monitor"), ctx)
    assert not result.ok


async def test_wait_for_window(ctx: ToolContext, desktop: FakeDesktop) -> None:
    desktop.windows = [CODE]
    result = await WaitForWindow().run(WaitForWindowParams(name="Visual Studio Code"), ctx)
    assert result.ok
    late = await WaitForWindow().run(WaitForWindowParams(name="Calculadora", timeout_s=0.5), ctx)
    assert not late.ok
