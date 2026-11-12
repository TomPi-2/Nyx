from __future__ import annotations

import pytest

from nyx.tools.audio_output import AudioOutput, AudioOutputParams
from nyx.tools.base import Category, GamePolicy, Risk, ToolContext
from nyx.winapi import launch
from tests.tools.fakes import FakeDesktop


def test_metadata() -> None:
    tool = AudioOutput()
    assert tool.name == "audio_output"
    assert tool.risk is Risk.GREEN
    assert tool.game_policy is GamePolicy.DEFERRED
    assert tool.category is Category.AUDIO
    assert tool.observe is True


async def test_opens_windows_sound_settings_and_explains_why(
    ctx: ToolContext, desktop: FakeDesktop
) -> None:
    tool = AudioOutput()
    res = await tool.run(AudioOutputParams(device="auriculares"), ctx)
    assert res.ok
    assert desktop.opened == ["ms-settings:sound"]
    assert desktop.focus_requests == [("Configuración", None)]
    assert "no permite" in res.message and "auriculares" in res.message
    assert res.display == "Ajustes de sonido"
    assert res.data == {"opened": "ms-settings:sound", "device": "auriculares"}


async def test_audio_output_handles_open_failure(
    ctx: ToolContext, desktop: FakeDesktop, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(_: str) -> None:
        raise OSError("bloqueado")

    monkeypatch.setattr(launch, "shell_open", boom)
    res = await AudioOutput().run(AudioOutputParams(), ctx)
    assert not res.ok
    assert "ajustes de sonido" in res.message
