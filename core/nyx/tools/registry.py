"""ToolRegistry: catálogo de herramientas disponibles."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from nyx.tools.base import Category, Tool


class ToolRegistry:
    def __init__(self, tools: Iterable[Tool[Any]] = ()) -> None:
        self._tools: dict[str, Tool[Any]] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: Tool[Any]) -> None:
        if tool.name in self._tools:
            raise ValueError(f"herramienta repetida: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool[Any] | None:
        return self._tools.get(name)

    def all(self) -> list[Tool[Any]]:
        return list(self._tools.values())

    def schemas(self, categories: set[Category] | None = None) -> list[dict[str, Any]]:
        return [
            t.schema()
            for t in self._tools.values()
            if t.llm_visible and (categories is None or t.category in categories)
        ]


def default_registry() -> ToolRegistry:
    from nyx.tools.alarms import CancelAlarm, ListAlarms
    from nyx.tools.app_action import AppAction
    from nyx.tools.audio_output import AudioOutput
    from nyx.tools.clipboard import Clipboard
    from nyx.tools.close_app import CloseApp
    from nyx.tools.copy_files import CopyFiles
    from nyx.tools.create_folder import CreateFolder
    from nyx.tools.delete_files import DeleteFiles
    from nyx.tools.find_files import FindFiles
    from nyx.tools.focus_window import FocusWindow
    from nyx.tools.get_weather import GetWeather
    from nyx.tools.install_app import InstallApp
    from nyx.tools.list_files import ListFiles
    from nyx.tools.media_control import MediaControl
    from nyx.tools.move_files import MoveFiles
    from nyx.tools.now_playing import NowPlayingTool
    from nyx.tools.nyx_control import NyxControl
    from nyx.tools.nyx_info import NyxInfo
    from nyx.tools.open_app import OpenApp
    from nyx.tools.open_nyx_settings import OpenNyxSettings
    from nyx.tools.open_path import OpenPath
    from nyx.tools.open_settings import OpenSettings
    from nyx.tools.open_url import OpenUrl
    from nyx.tools.pending import Pending
    from nyx.tools.rename_file import RenameFile
    from nyx.tools.run_powershell import RunPowershell
    from nyx.tools.save_note import SaveNote
    from nyx.tools.screenshot import Screenshot
    from nyx.tools.send_hotkey import SendHotkey
    from nyx.tools.set_alarm import SetAlarm
    from nyx.tools.set_brightness import SetBrightness
    from nyx.tools.set_timer import SetTimer
    from nyx.tools.set_volume import SetVolume
    from nyx.tools.stopwatch import Stopwatch
    from nyx.tools.system_info import SystemInfo
    from nyx.tools.system_power import SystemPower
    from nyx.tools.toggle_bluetooth import ToggleBluetooth
    from nyx.tools.toggle_wifi import ToggleWifi
    from nyx.tools.type_text import TypeText
    from nyx.tools.ui_action import UiAction
    from nyx.tools.undo import UndoLast
    from nyx.tools.wait_for_window import WaitForWindow
    from nyx.tools.web_search import WebSearch
    from nyx.tools.window_layout import WindowLayout
    from nyx.winapi.location import Locator

    return ToolRegistry(
        [
            OpenApp(),
            FocusWindow(),
            WindowLayout(),
            WaitForWindow(),
            OpenUrl(),
            OpenSettings(),
            OpenNyxSettings(),
            Pending(),
            OpenPath(),
            SetVolume(),
            SetBrightness(),
            MediaControl(),
            NowPlayingTool(),
            AudioOutput(),
            Screenshot(),
            CloseApp(),
            CreateFolder(),
            SaveNote(),
            ListFiles(),
            FindFiles(),
            MoveFiles(),
            CopyFiles(),
            RenameFile(),
            SetAlarm(),
            SetTimer(),
            ListAlarms(),
            CancelAlarm(),
            Stopwatch(),
            NyxInfo(),
            NyxControl(),
            GetWeather(locator=Locator()),
            SystemInfo(),
            SystemPower(),
            ToggleWifi(),
            ToggleBluetooth(),
            Clipboard(),
            TypeText(),
            SendHotkey(),
            AppAction(),
            DeleteFiles(),
            RunPowershell(),
            InstallApp(),
            UiAction(),
            WebSearch(),
            UndoLast(),
        ]
    )
