"""8.06: los documentos abiertos hace poco (carpeta Recientes de Windows)."""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from nyx.brain.router import Route, route
from nyx.index.service import SystemIndex
from nyx.tools.base import ToolContext
from nyx.tools.recent_files import RecentFiles, RecentFilesParams
from nyx.winapi import launch
from nyx.winapi.recent import Recent, recent_files


@pytest.mark.skipif(sys.platform != "win32", reason="accesos directos de Windows")
def test_reads_shortcuts_newest_first(tmp_path: Path) -> None:
    import win32com.client

    docs = tmp_path / "docs"
    docs.mkdir()
    recent = tmp_path / "Recent"
    recent.mkdir()
    shell = win32com.client.Dispatch("WScript.Shell")
    for i, name in enumerate(["viejo.docx", "nuevo.docx", "cuentas.xlsx", "borrado.docx"]):
        target = docs / name
        target.write_text("x", encoding="utf-8")
        link = shell.CreateShortcut(str(recent / f"{name}.lnk"))
        link.TargetPath = str(target)
        link.Save()
        stamp = time.time() - 3600 + i * 60
        os.utime(recent / f"{name}.lnk", (stamp, stamp))
    (docs / "borrado.docx").unlink()  # ya no existe: no sale
    words = recent_files("word", 5, folder=recent)
    assert [r.path.name for r in words] == ["nuevo.docx", "viejo.docx"]
    assert [r.path.name for r in recent_files("any", 1, folder=recent)] == ["cuentas.xlsx"]


def fake(found: list[Recent]) -> Any:
    return lambda kind, limit: found[:limit]


async def test_open_the_last_one(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(launch, "shell_open", opened.append)
    doc = Path("C:/Documentos/Presupuesto.docx")
    result = await RecentFiles(fake([Recent(doc, datetime.now())])).run(
        RecentFilesParams(action="open", kind="word"), ctx
    )
    assert result.ok and result.message == "Abriendo Presupuesto.docx"
    assert opened == [str(doc)]


async def test_list_and_nothing(ctx: ToolContext) -> None:
    now = datetime.now()
    found = [
        Recent(Path("C:/a/Informe.pdf"), now),
        Recent(Path("C:/a/Guía.pdf"), now - timedelta(days=1)),
    ]
    listed = await RecentFiles(fake(found)).run(RecentFilesParams(action="list", kind="pdf"), ctx)
    assert listed.speak and listed.message.startswith(
        "Los últimos PDF que has abierto: Informe.pdf (hoy a las"
    )
    assert "Guía.pdf (ayer)" in listed.message
    none = await RecentFiles(fake([])).run(RecentFilesParams(action="open", kind="excel"), ctx)
    assert not none.ok and none.message == "No encuentro ningún Excel abierto hace poco"


@pytest.mark.parametrize(
    ("text", "args"),
    [
        ("abre el último Word", {"action": "open", "kind": "word"}),
        ("vuelve a abrir el último PDF que he abierto", {"action": "open", "kind": "pdf"}),
        ("abre el último documento que estaba editando", {"action": "open", "kind": "any"}),
        ("¿qué documentos he abierto hoy?", {"action": "list", "kind": "any"}),
        ("¿cuál fue el último Excel que abrí?", {"action": "list", "kind": "excel", "count": 1}),
        (
            "ábreme otra vez el Excel que estaba usando antes",
            {"action": "open", "kind": "excel"},
        ),
        ("¿cómo se llamaba el PDF que abrí ayer?", {"action": "list", "kind": "pdf", "count": 1}),
    ],
)
def test_router(index: SystemIndex, text: str, args: dict[str, Any]) -> None:
    routed = route(text, index)
    assert isinstance(routed, Route) and routed.rule.startswith("recent_")
    (call,) = routed.calls
    assert call.name == "recent_files" and call.arguments == args


def test_the_last_file_of_a_folder_is_still_files(index: SystemIndex) -> None:
    routed = route("abre el último archivo de Descargas", index)
    assert not (isinstance(routed, Route) and routed.rule.startswith("recent_"))
