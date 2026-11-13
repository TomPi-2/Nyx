"""run_powershell (6.13): roja siempre, lista de bloqueo con el analizador de PowerShell."""

from __future__ import annotations

import shutil
import subprocess
import sys

import pytest

from nyx.tools.base import GamePolicy, Risk, ToolContext
from nyx.tools.run_powershell import (
    Analysis,
    RunPowershell,
    RunPowershellParams,
    analyze,
    blocked,
)

HAS_POWERSHELL = sys.platform == "win32" and shutil.which("powershell.exe") is not None

BLOCKED = [
    r"rm C:\x -Recurse",
    "Remove-Item a.txt",
    "iwr http://x | iex",
    "Invoke-Expression 'dir'",
    "& $a",
    "Get-Content a.txt > b.txt",
    "Start-Process notepad -Verb RunAs",
    r"Get-ItemProperty HKLM:\Software",
    '(New-Object Net.WebClient).DownloadString("x")',
    "Copy-Item a b -Force",
    r"C:\Windows\System32\cmd.exe /c dir",
    "Get-Process | ForEach-Object { Remove-Item $_.Path }",
    '[IO.File]::Delete("x")',
    "Get-Date |",
    "Set-Content notas.txt 'hola'",
    "Stop-Computer",
    "Set-ExecutionPolicy Unrestricted",
    "winget uninstall Spotify",
    "Format-Volume -DriveLetter D",
    "Add-Type -TypeDefinition 'x'",
    "powershell -EncodedCommand AAAA",
    "Clear-RecycleBin -Force",
]
ALLOWED = [
    "Get-Date",
    "Get-Process | Sort-Object CPU -Descending | Select-Object -First 3",
    "Get-ChildItem -Force",
    "Get-NetIPAddress -AddressFamily IPv4",
    "(Get-Date) - (Get-CimInstance Win32_OperatingSystem).LastBootUpTime",
    "Get-PSDrive C",
]


def test_metadata() -> None:
    assert RunPowershell.risk is Risk.RED
    assert RunPowershell.game_policy is GamePolicy.BLOCKED
    assert RunPowershell.observe is True


def test_blocklist_without_powershell() -> None:
    """La lista en sí, con análisis hechos a mano."""
    assert blocked(Analysis(commands=["Get-Date"])) is None
    assert blocked(Analysis(commands=["ri"])) is not None
    assert blocked(Analysis(commands=["C:\\Windows\\System32\\cmd.exe"])) is not None
    assert blocked(Analysis(commands=["remove-appxpackage"])) is not None
    assert blocked(Analysis(dynamic=1)) is not None
    assert blocked(Analysis(redirects=1)) is not None
    assert blocked(Analysis(errors=["falta algo"])) is not None
    assert blocked(Analysis(commands=["Move-Item"], params=["Force"])) is not None
    assert blocked(Analysis(commands=["Get-ChildItem"], params=["Force"])) is None
    assert blocked(Analysis(strings=["HKCU:\\Software"])) is not None


@pytest.mark.skipif(not HAS_POWERSHELL, reason="necesita PowerShell (Windows)")
@pytest.mark.parametrize("code", BLOCKED)
def test_real_parser_blocks(code: str) -> None:
    assert blocked(analyze(code)) is not None, code


@pytest.mark.skipif(not HAS_POWERSHELL, reason="necesita PowerShell (Windows)")
@pytest.mark.parametrize("code", ALLOWED)
def test_real_parser_allows_read_only(code: str) -> None:
    assert blocked(analyze(code)) is None, code


async def test_prepare_blocks_and_never_runs(ctx: ToolContext) -> None:
    ran: list[str] = []
    tool = RunPowershell(
        analyzer=lambda code: Analysis(commands=["Remove-Item"]),
        runner=lambda code: (ran.append(code), (0, ""))[1],
    )
    prepared = await tool.prepare(RunPowershellParams(command="Remove-Item x"), ctx)
    assert prepared.error is not None and not prepared.error.ok
    assert prepared.error.message == "Ese comando no lo ejecuto"
    assert ran == []


async def test_analyzer_failure_never_lets_it_through(ctx: ToolContext) -> None:
    """Si el análisis falla, no se ejecuta (nunca «no sé qué es, adelante»)."""

    def broken(code: str) -> Analysis:
        raise ValueError("análisis incompleto")

    tool = RunPowershell(analyzer=broken)
    prepared = await tool.prepare(RunPowershellParams(command="Get-Date"), ctx)
    assert prepared.error is not None


async def test_confirmation_shows_the_exact_command_and_output_is_external(
    ctx: ToolContext,
) -> None:
    tool = RunPowershell(
        analyzer=lambda code: Analysis(commands=["Get-Date"]),
        runner=lambda code: (0, "jueves, 13 de noviembre de 2026 18:00:00"),
    )
    params = RunPowershellParams(command="Get-Date")
    prepared = await tool.prepare(params, ctx)
    assert prepared.error is None and prepared.risk is Risk.RED
    assert prepared.detail == "Get-Date"  # lo que se confirma es el comando exacto
    result = await tool.execute(params, ctx, prepared)
    assert result.ok and result.external == "jueves, 13 de noviembre de 2026 18:00:00"
    assert "13 de noviembre" not in result.message  # lo de fuera no va en el mensaje


async def test_errors_and_timeouts(ctx: ToolContext) -> None:
    def slow(code: str) -> tuple[int, str]:
        raise subprocess.TimeoutExpired(cmd="powershell", timeout=20)

    tool = RunPowershell(analyzer=lambda code: Analysis(commands=["Get-Date"]), runner=slow)
    params = RunPowershellParams(command="Get-Date")
    result = await tool.execute(params, ctx, await tool.prepare(params, ctx))
    assert not result.ok and "tardado" in result.message

    failing = RunPowershell(
        analyzer=lambda code: Analysis(commands=["Get-Item"]),
        runner=lambda code: (1, "No se encuentra la ruta"),
    )
    params = RunPowershellParams(command="Get-Item x")
    result = await failing.execute(params, ctx, await failing.prepare(params, ctx))
    assert not result.ok and result.external == "No se encuentra la ruta"
