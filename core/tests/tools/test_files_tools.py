"""Herramientas de archivos con archivos reales en carpetas temporales."""

import os
import time
from pathlib import Path

import pytest

from nyx.executor import Confirmation, Executor, ToolCall
from nyx.safety.action_log import ActionLog
from nyx.safety.paths import PathPolicy
from nyx.tools import delete_files as delete_module
from nyx.tools import find_files as find_module
from nyx.tools.base import ToolContext
from nyx.tools.create_folder import valid_name
from nyx.tools.files import FileSelection, select, unique_target
from nyx.tools.registry import default_registry


def touch(path: Path, age_s: float = 0.0, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    when = time.time() - age_s
    os.utime(path, (when, when))
    return path


@pytest.fixture
def downloads(ctx: ToolContext) -> Path:
    folder = Path(ctx.index.confident(ctx.index.resolve("descargas")).entry.launch.value)  # type: ignore[union-attr]
    for i in range(6):
        touch(folder / f"archivo{i}.txt", age_s=100 - i)  # archivo5 es el más reciente
    touch(folder / "foto.jpg", age_s=200)
    touch(folder / "factura luz.pdf", age_s=300)
    return folder


@pytest.fixture
def trash(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """La papelera de verdad no se toca en las pruebas."""
    sent: list[str] = []

    def fake(path: str) -> None:
        sent.append(path)
        p = Path(path)
        if p.is_dir():
            import shutil

            shutil.rmtree(p)
        else:
            p.unlink()

    monkeypatch.setattr(delete_module, "send2trash", fake)
    return sent


def executor(
    ctx: ToolContext, answers: list[bool] | None = None, log_dir: Path | None = None
) -> Executor:
    asked: list[Confirmation] = []

    async def confirm(c: Confirmation) -> bool:
        asked.append(c)
        return answers.pop(0) if answers else False

    ex = Executor(
        default_registry(),
        ctx,
        confirm=confirm,
        action_log=ActionLog(log_dir) if log_dir else None,
    )
    ex.asked = asked  # type: ignore[attr-defined]
    return ex


# --- selección ---


def test_selection_newest_kind_and_names(ctx: ToolContext, downloads: Path) -> None:
    folder, items = select(FileSelection(folder="descargas", newest=2), ctx)  # type: ignore[misc]
    assert folder == downloads
    assert [p.name for p in items] == ["archivo5.txt", "archivo4.txt"]
    _, images = select(FileSelection(folder="descargas", kind="images"), ctx)  # type: ignore[misc]
    assert [p.name for p in images] == ["foto.jpg"]
    _, named = select(FileSelection(folder="descargas", names=["factura"]), ctx)  # type: ignore[misc]
    assert [p.name for p in named] == ["factura luz.pdf"]


def test_selection_needs_something(ctx: ToolContext, downloads: Path) -> None:
    result = select(FileSelection(folder="descargas"), ctx)
    assert not isinstance(result, tuple) and not result.ok


def test_unique_target_never_overwrites(tmp_path: Path) -> None:
    touch(tmp_path / "a.txt")
    touch(tmp_path / "a (2).txt")
    assert unique_target(tmp_path, "a.txt").name == "a (3).txt"
    assert unique_target(tmp_path, "b.txt").name == "b.txt"


@pytest.mark.parametrize(
    ("name", "ok"), [("Fondos", True), ("a/b", False), ("CON", False), ("x?", False)]
)
def test_folder_names(name: str, ok: bool) -> None:
    assert (valid_name(name) is not None) is ok


# --- herramientas a través del ejecutor (como en Nyx) ---


async def test_create_folder(ctx: ToolContext, downloads: Path) -> None:
    ex = executor(ctx)
    result = await ex.run(
        ToolCall("create_folder", {"name": "Fondos nuevos", "parent": "descargas"})
    )
    assert result.ok and (downloads / "Fondos nuevos").is_dir()
    again = await ex.run(
        ToolCall("create_folder", {"name": "Fondos nuevos", "parent": "descargas"})
    )
    assert not again.ok and "Ya existe" in again.message


async def test_list_files_defaults_to_newest(ctx: ToolContext, downloads: Path) -> None:
    result = await executor(ctx).run(ToolCall("list_files", {"folder": "descargas"}))
    assert result.ok and len(result.data["paths"]) == 8
    assert result.secondary is not None and result.secondary.startswith("archivo5.txt")


async def test_move_and_undo(ctx: ToolContext, downloads: Path, tmp_path: Path) -> None:
    ex = executor(ctx)
    docs = tmp_path / "Documentos"
    touch(docs / "archivo5.txt", text="ya estaba")  # conflicto: no se sobrescribe
    result = await ex.run(
        ToolCall("move_files", {"folder": "descargas", "newest": 2, "destination": "documentos"})
    )
    assert result.ok and result.data["undo_id"]
    assert (docs / "archivo5 (2).txt").exists() and (docs / "archivo4.txt").exists()
    assert (docs / "archivo5.txt").read_text(encoding="utf-8") == "ya estaba"
    assert not (downloads / "archivo5.txt").exists()
    undone = await ex.run(ToolCall("undo"))
    assert undone.ok
    assert (downloads / "archivo5.txt").exists() and (downloads / "archivo4.txt").exists()
    assert not (docs / "archivo4.txt").exists()
    assert not (await ex.run(ToolCall("undo"))).ok  # ya no queda nada


async def test_copy_and_undo_sends_copies_to_trash(
    ctx: ToolContext, downloads: Path, tmp_path: Path, trash: list[str]
) -> None:
    ex = executor(ctx)
    result = await ex.run(
        ToolCall(
            "copy_files", {"folder": "descargas", "kind": "images", "destination": "documentos"}
        )
    )
    assert result.ok and (tmp_path / "Documentos" / "foto.jpg").exists()
    assert (downloads / "foto.jpg").exists()
    await ex.run(ToolCall("undo"))
    assert trash == [str(tmp_path / "Documentos" / "foto.jpg")]
    assert (downloads / "foto.jpg").exists()


async def test_rename_keeps_extension_and_undo(ctx: ToolContext, downloads: Path) -> None:
    ex = executor(ctx)
    result = await ex.run(
        ToolCall("rename_file", {"folder": "descargas", "name": "factura", "new_name": "luz enero"})
    )
    assert result.ok and (downloads / "luz enero.pdf").exists()
    await ex.run(ToolCall("undo"))
    assert (downloads / "factura luz.pdf").exists()


async def test_delete_asks_and_uses_trash(
    ctx: ToolContext, downloads: Path, trash: list[str], tmp_path: Path
) -> None:
    ex = executor(ctx, answers=[False, True], log_dir=tmp_path / "log")
    call = ToolCall("delete_files", {"folder": "descargas", "newest": 1})
    cancelled = await ex.run(call, phrase="borra el último archivo de descargas")
    assert not cancelled.ok and cancelled.data["cancelled"]
    assert (downloads / "archivo5.txt").exists() and trash == []
    confirmed = await ex.run(call)
    assert confirmed.ok and trash == [str(downloads / "archivo5.txt")]
    asked = ex.asked  # type: ignore[attr-defined]
    assert asked[0].summary == "Mandar a la papelera «archivo5.txt»"
    assert not asked[0].click_only
    decisions = [r["decision"] for r in ActionLog(tmp_path / "log").read()]
    assert decisions == ["cancelled", "confirmed"]


async def test_delete_folder_counts_contents_click_only(
    ctx: ToolContext, downloads: Path, trash: list[str]
) -> None:
    for i in range(60):
        touch(downloads / "Grande" / f"{i}.txt")
    ex = executor(ctx, answers=[True])
    result = await ex.run(
        ToolCall(
            "delete_files",
            {"folder": str(downloads), "names": ["Grande"], "include_folders": True},
        )
    )
    assert result.ok
    asked = ex.asked  # type: ignore[attr-defined]
    assert asked[0].click_only  # más de 50 archivos: solo con clic
    assert "60 archivos" in asked[0].summary


async def test_protected_paths_are_blocked(ctx: ToolContext, downloads: Path) -> None:
    ctx.paths = PathPolicy(home=Path.home(), protected_trees=[downloads])
    result = await executor(ctx, answers=[True]).run(
        ToolCall("delete_files", {"folder": "descargas", "newest": 1})
    )
    assert not result.ok and "protegida" in result.message
    assert (downloads / "archivo5.txt").exists()


async def test_find_files_uses_search_backend(
    ctx: ToolContext, monkeypatch: pytest.MonkeyPatch, downloads: Path
) -> None:
    seen: list[str] = []

    def fake_search(query: str, roots: list[Path], limit: int) -> tuple[list[Path], str]:
        seen.append(query)
        return [downloads / "factura luz.pdf", downloads / "foto.jpg"], "windows"

    monkeypatch.setattr(find_module.search, "search", fake_search)
    result = await executor(ctx).run(
        ToolCall("find_files", {"query": "factura", "kind": "documents"})
    )
    assert result.ok and result.display == "factura luz.pdf"
    assert seen == ["factura"]


async def test_delete_can_be_undone_from_the_recycle_bin(
    ctx: ToolContext, downloads: Path, trash: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    restored: list[list[Path]] = []

    def fake_restore(paths: list[Path]) -> list[Path]:
        restored.append(paths)
        for p in paths:
            touch(p)
        return paths

    monkeypatch.setattr(delete_module.recycle, "restore", fake_restore)
    ex = executor(ctx, answers=[True])
    result = await ex.run(ToolCall("delete_files", {"folder": "descargas", "newest": 1}))
    assert result.ok and result.data["undo_id"]
    undone = await ex.run(ToolCall("undo"))
    assert undone.ok and "Recuperado" in undone.message
    assert restored == [[downloads / "archivo5.txt"]] and (downloads / "archivo5.txt").exists()
