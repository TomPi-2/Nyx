from __future__ import annotations

from nyx.tools.base import Category, GamePolicy, Risk, ToolContext
from nyx.tools.now_playing import NowPlaying, NowPlayingParams, NowPlayingTool, app_label


def test_metadata() -> None:
    tool = NowPlayingTool()
    assert tool.name == "now_playing"
    assert tool.risk is Risk.GREEN
    assert tool.game_policy is GamePolicy.ALLOWED
    assert tool.category is Category.AUDIO
    assert tool.observe is True


def test_app_label() -> None:
    assert app_label("Spotify.exe") == "Spotify"
    assert app_label("OperaSoftware.OperaGXWebBrowser.1751") == "Opera GX"
    assert app_label("OperaStable") == "Opera"
    assert app_label(r"C:\Program Files\OtherApp.EXE") == "OtherApp"
    assert app_label("Pkg!AppId") == "AppId"
    assert app_label("") == "otra app"


async def test_playing_paused_and_nothing(ctx: ToolContext) -> None:
    playing = NowPlayingTool(
        reader=lambda: NowPlaying("Bohemian Rhapsody", "Queen", "Spotify", True)
    )
    res = await playing.run(NowPlayingParams(), ctx)
    assert res.ok
    assert res.message == "Suena «Bohemian Rhapsody» de Queen en Spotify"
    assert res.display == "Bohemian Rhapsody"
    assert res.secondary == "Queen · Spotify"
    assert res.data == {"playing": True}

    paused = NowPlayingTool(reader=lambda: NowPlaying("Lo-fi Beats", "", "Chrome", False))
    res_paused = await paused.run(NowPlayingParams(), ctx)
    assert res_paused.ok
    assert res_paused.message == "En pausa: «Lo-fi Beats» en Chrome"
    assert res_paused.secondary == "Chrome"
    assert res_paused.data == {"playing": False}

    empty = NowPlayingTool(reader=lambda: None)
    res_empty = await empty.run(NowPlayingParams(), ctx)
    assert res_empty.ok
    assert res_empty.message == "No suena nada ahora"
    assert res_empty.display == "No suena nada"


async def test_now_playing_error_is_contained(ctx: ToolContext) -> None:
    def boom() -> NowPlaying | None:
        raise RuntimeError("sin smtc")

    tool = NowPlayingTool(reader=boom)
    res = await tool.run(NowPlayingParams(), ctx)
    assert not res.ok
    assert "qué suena" in res.message
