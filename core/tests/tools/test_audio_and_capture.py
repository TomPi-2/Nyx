import struct
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from nyx.tools import screenshot as screenshot_module
from nyx.tools.base import ToolContext
from nyx.tools.media_control import MediaControl, MediaControlParams
from nyx.tools.screenshot import Screenshot, ScreenshotParams, region_for
from nyx.tools.set_volume import SetVolume, SetVolumeParams
from nyx.winapi.capture import Shot, to_dib
from nyx.winapi.windows import Window
from tests.tools.fakes import FakeDesktop


async def test_volume_level_change_and_mute(ctx: ToolContext, desktop: FakeDesktop) -> None:
    tool = SetVolume()
    assert (await tool.run(SetVolumeParams(level=40), ctx)).data["level"] == 40
    assert (await tool.run(SetVolumeParams(change=10), ctx)).data["level"] == 50
    assert (await tool.run(SetVolumeParams(change=80), ctx)).data["level"] == 100
    muted = await tool.run(SetVolumeParams(mute=True), ctx)
    assert muted.data["muted"] and muted.display is None


def test_volume_params_need_one_action() -> None:
    with pytest.raises(ValidationError):
        SetVolumeParams()
    with pytest.raises(ValidationError):
        SetVolumeParams(level=10, change=5)
    with pytest.raises(ValidationError):
        SetVolumeParams(level=150)


async def test_app_volume(ctx: ToolContext, desktop: FakeDesktop) -> None:
    desktop.sessions = {"spotify.exe": 100}
    result = await SetVolume().run(SetVolumeParams(app="spotify", level=30), ctx)
    assert result.ok and desktop.sessions["spotify.exe"] == 30
    louder = await SetVolume().run(SetVolumeParams(app="spotify", change=10), ctx)
    assert louder.ok and louder.data["level"] == 40 and desktop.sessions["spotify.exe"] == 40
    silent = await SetVolume().run(SetVolumeParams(app="discord", mute=True), ctx)
    assert not silent.ok  # no está sonando


async def test_media_keys(ctx: ToolContext, desktop: FakeDesktop) -> None:
    for action in ("play_pause", "next", "previous"):
        assert (await MediaControl().run(MediaControlParams(action=action), ctx)).ok  # type: ignore[arg-type]
    assert desktop.keys == ["play_pause", "next", "previous"]


def test_screenshot_regions(desktop: FakeDesktop) -> None:
    desktop.windows, desktop.fg = [Window(7, "Juego", "game.exe")], 7
    desktop.rects = {7: (2600, 10, 3000, 400)}
    assert region_for("primary") == (0, 0, 2560, 1440)
    assert region_for("all") == (0, 0, 4480, 1440)
    assert region_for("current") == (2560, 0, 4480, 1080)  # el monitor de la ventana activa
    assert region_for("window") == (2600, 10, 3000, 400)


async def test_screenshot_shows_bubble(
    ctx: ToolContext, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    taken: list[tuple[str, Path]] = []

    def fake_take(target: str, folder: Path) -> Path:
        taken.append((target, folder))
        return folder / "x.png"

    monkeypatch.setattr(screenshot_module, "take", fake_take)
    monkeypatch.setattr(screenshot_module, "pictures_dir", lambda: tmp_path)
    result = await Screenshot().run(ScreenshotParams(target="primary"), ctx)
    assert result.ok and result.display == "Captura guardada"
    assert taken == [("primary", tmp_path / "Capturas" / "Nyx")]


def test_dib_is_bottom_up_32_bit() -> None:
    pixels = np.zeros((2, 3, 4), dtype=np.uint8)
    pixels[0, :, 0] = 255  # fila de arriba azul
    dib = to_dib(Shot(pixels, 3, 2))
    size, width, height, _, bits = struct.unpack("<IiiHH", dib[:16])
    assert (size, width, height, bits) == (40, 3, 2, 32)
    body = dib[40:]
    assert body[3 * 4] == 255 and body[0] == 0  # la fila de arriba va al final
