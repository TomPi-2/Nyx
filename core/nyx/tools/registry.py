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
            if categories is None or t.category in categories
        ]


def default_registry() -> ToolRegistry:
    from nyx.tools.app_action import AppAction
    from nyx.tools.close_app import CloseApp
    from nyx.tools.copy_files import CopyFiles
    from nyx.tools.create_folder import CreateFolder
    from nyx.tools.delete_files import DeleteFiles
    from nyx.tools.find_files import FindFiles
    from nyx.tools.focus_window import FocusWindow
    from nyx.tools.list_files import ListFiles
    from nyx.tools.media_control import MediaControl
    from nyx.tools.move_files import MoveFiles
    from nyx.tools.open_app import OpenApp
    from nyx.tools.open_path import OpenPath
    from nyx.tools.open_settings import OpenSettings
    from nyx.tools.open_url import OpenUrl
    from nyx.tools.rename_file import RenameFile
    from nyx.tools.screenshot import Screenshot
    from nyx.tools.send_hotkey import SendHotkey
    from nyx.tools.set_alarm import SetAlarm
    from nyx.tools.set_timer import SetTimer
    from nyx.tools.set_volume import SetVolume
    from nyx.tools.undo import UndoLast
    from nyx.tools.wait_for_window import WaitForWindow
    from nyx.tools.window_layout import WindowLayout

    return ToolRegistry(
        [
            OpenApp(),
            FocusWindow(),
            WindowLayout(),
            WaitForWindow(),
            OpenUrl(),
            OpenSettings(),
            OpenPath(),
            SetVolume(),
            MediaControl(),
            Screenshot(),
            CloseApp(),
            CreateFolder(),
            ListFiles(),
            FindFiles(),
            MoveFiles(),
            CopyFiles(),
            RenameFile(),
            SetAlarm(),
            SetTimer(),
            SendHotkey(),
            AppAction(),
            DeleteFiles(),
            UndoLast(),
        ]
    )
