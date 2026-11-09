"""Sustitutos de Windows para probar las herramientas sin tocar el escritorio."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from nyx.index.model import Launch
from nyx.winapi import focus, launch, media, windows
from nyx.winapi.windows import Monitor, Rect, Window


@dataclass
class FakeDesktop:
    launched: list[Launch] = field(default_factory=list)
    opened: list[str] = field(default_factory=list)
    windows: list[Window] = field(default_factory=list)
    activated: list[int] = field(default_factory=list)
    shown: list[tuple[int, str]] = field(default_factory=list)
    placed: list[tuple[int, Rect]] = field(default_factory=list)
    rects: dict[int, Rect] = field(default_factory=dict)
    maximized: set[int] = field(default_factory=set)
    screens: list[Monitor] = field(
        default_factory=lambda: [
            Monitor((0, 0, 2560, 1440), (0, 0, 2560, 1400), True),
            Monitor((2560, 0, 4480, 1080), (2560, 0, 4480, 1040), False),
        ]
    )
    fg: int | None = None
    volume: int = 50
    muted: bool = False
    sessions: dict[str, int] = field(default_factory=dict)
    keys: list[str] = field(default_factory=list)
    launch_error: bool = False
    focus_requests: list[tuple[str, str | None]] = field(default_factory=list)

    def install(self, mp: pytest.MonkeyPatch) -> None:
        def fake_launch(spec: Launch) -> None:
            if self.launch_error:
                raise OSError("no se pudo")
            self.launched.append(spec)

        mp.setattr(launch, "launch", fake_launch)
        mp.setattr(launch, "shell_open", self.opened.append)
        mp.setattr(
            focus,
            "request",
            lambda name, process, before, **_: self.focus_requests.append((name, process)),
        )
        mp.setattr(focus, "default_browser_process", lambda: "opera.exe")
        mp.setattr(windows, "list_windows", lambda: list(self.windows))
        mp.setattr(windows, "activate", lambda h: self.activated.append(h) or True)
        mp.setattr(windows, "show", lambda h, how: self.shown.append((h, how)))
        mp.setattr(windows, "place", lambda h, r: self.placed.append((h, r)))
        mp.setattr(windows, "window_rect", lambda h: self.rects[h])
        mp.setattr(windows, "is_maximized", lambda h: h in self.maximized)
        mp.setattr(windows, "monitors", lambda: list(self.screens))
        mp.setattr(
            windows,
            "foreground",
            lambda: next((w for w in self.windows if w.hwnd == self.fg), None),
        )
        mp.setattr(media, "get_master", lambda: (self.volume, self.muted))
        mp.setattr(media, "set_master", self._set_master)
        mp.setattr(media, "app_sessions", lambda: sorted(self.sessions))
        mp.setattr(media, "set_app", self._set_app)
        mp.setattr(media, "press_media_key", self.keys.append)

    def _set_master(self, level: int | None = None, mute: bool | None = None) -> tuple[int, bool]:
        if level is not None:
            self.volume = max(0, min(100, level))
        if mute is not None:
            self.muted = mute
        return self.volume, self.muted

    def _set_app(
        self,
        process: str,
        level: int | None = None,
        mute: bool | None = None,
        change: int | None = None,
    ) -> int | None:
        if process not in self.sessions:
            return None
        if change is not None:
            level = self.sessions[process] + change
        if level is not None:
            self.sessions[process] = max(0, min(100, level))
        if mute:
            self.sessions[process] = 0
        return self.sessions[process]


@pytest.fixture
def desktop(monkeypatch: pytest.MonkeyPatch) -> FakeDesktop:
    fake = FakeDesktop()
    fake.install(monkeypatch)
    return fake
