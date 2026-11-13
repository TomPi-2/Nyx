"""install_app (6.14): winget, roja siempre, el paquete exacto o no se adivina."""

from __future__ import annotations

from typing import Any

from nyx.tools.base import GamePolicy, Risk, ToolContext
from nyx.tools.install_app import (
    InstallApp,
    InstallAppParams,
    Package,
    choose,
    parse_table,
    publisher,
)

SEARCH = (
    "   - \r   \\ \r"
    "Nombre                     Id                   Versión                Origen\n"
    "------------------------------------------------------------------------------\n"
    "VLC media player           VideoLAN.VLC         3.0.24                 winget\n"
    "VLC media player (Nightly) VideoLAN.VLC.Nightly 4.0.0-nightly.20261102 winget\n"
)
SHOW = "Encontrado VLC media player [VideoLAN.VLC]\nVersión: 3.0.24\nEditor: VideoLAN\n"


class FakeWinget:
    def __init__(self, search: str = SEARCH, code: int = 0) -> None:
        self.search = search
        self.code = code
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str], *_: Any) -> tuple[int, str]:
        self.calls.append(args)
        if args[0] in ("search", "list"):
            return 0, self.search
        if args[0] == "show":
            return 0, SHOW
        return self.code, "ok"


def test_metadata() -> None:
    assert InstallApp.risk is Risk.RED
    assert InstallApp.game_policy is GamePolicy.BLOCKED


def test_parse_table_and_publisher() -> None:
    rows = parse_table(SEARCH)
    assert rows == [
        Package("VLC media player", "VideoLAN.VLC", "3.0.24"),
        Package("VLC media player (Nightly)", "VideoLAN.VLC.Nightly", "4.0.0-nightly.20261102"),
    ]
    assert parse_table("No se encontró ningún paquete que coincida.") == []
    assert publisher(SHOW) == "VideoLAN"
    assert publisher("Publisher: Spotify AB\n") == "Spotify AB"


def test_choose_never_guesses() -> None:
    rows = parse_table(SEARCH)
    assert choose(rows, "VLC media player") == rows[0]  # se llama igual
    many = choose(rows, "VLC")
    assert isinstance(many, list) and len(many) == 2  # no se adivina
    assert choose([], "VLC") is None


async def test_install_confirms_the_exact_package(ctx: ToolContext) -> None:
    fake = FakeWinget()
    tool = InstallApp(runner=fake)
    params = InstallAppParams(action="install", name="VLC media player")
    prepared = await tool.prepare(params, ctx)
    assert prepared.error is None and prepared.risk is Risk.RED
    assert prepared.summary == "Instalar VLC media player"
    assert prepared.detail == "VideoLAN · VideoLAN.VLC · 3.0.24"
    result = await tool.execute(params, ctx, prepared)
    assert result.ok and result.display == "Instalado VLC media player"
    run = fake.calls[-1]
    assert run[:4] == ["install", "--id", "VideoLAN.VLC", "-e"]
    assert "--silent" in run and "--force" not in run


async def test_ambiguous_or_missing(ctx: ToolContext) -> None:
    tool = InstallApp(runner=FakeWinget())
    prepared = await tool.prepare(InstallAppParams(action="install", name="VLC"), ctx)
    assert prepared.error is not None and "varios" in prepared.error.message
    nothing = InstallApp(runner=FakeWinget(search="No se encontró ningún paquete."))
    prepared = await nothing.prepare(InstallAppParams(action="uninstall", name="Zoom"), ctx)
    assert prepared.error is not None and "instalado" in prepared.error.message


async def test_uninstall_uses_list_and_reports_failure(ctx: ToolContext) -> None:
    fake = FakeWinget(code=1)
    tool = InstallApp(runner=fake)
    params = InstallAppParams(action="uninstall", name="VideoLAN.VLC")
    prepared = await tool.prepare(params, ctx)
    assert fake.calls[0][0] == "list"
    result = await tool.execute(params, ctx, prepared)
    assert not result.ok and result.message == "No he podido desinstalar VLC media player"
