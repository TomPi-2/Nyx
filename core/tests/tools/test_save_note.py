"""save_note (6.28): nota nueva en Documentos/Notas de Nyx, sin sobrescribir nunca."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

import pytest

from nyx.tools import save_note
from nyx.tools.base import GamePolicy, Risk, ToolContext
from nyx.tools.save_note import NOTES_FOLDER, SaveNote, SaveNoteParams, file_stem

TODAY = date(2026, 11, 13)


def tool(docs: Path | None, opened: list[Path]) -> SaveNote:
    return SaveNote(documents=lambda: docs, opener=opened.append, today=lambda: TODAY)


def test_metadata() -> None:
    assert SaveNote.risk is Risk.YELLOW  # con Deshacer (a la papelera)
    assert SaveNote.game_policy is GamePolicy.DEFERRED  # no abre nada sobre el juego


@pytest.mark.parametrize(
    ("title", "stem"),
    [
        ("Tortilla de patatas", "Tortilla de patatas (13-11-2026)"),
        ('Receta: "la" mejor/peor?', "Receta la mejor peor (13-11-2026)"),
        ("con", "Nota (13-11-2026)"),
        ("...", "Nota (13-11-2026)"),
        ("x" * 200, "x" * 60 + " (13-11-2026)"),
    ],
)
def test_file_stem(title: str, stem: str) -> None:
    assert file_stem(title, TODAY) == stem


async def test_saves_opens_and_never_overwrites(
    tmp_path: Path, ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[Path] = []
    t = tool(tmp_path, opened)
    params = SaveNoteParams(title="Tortilla de patatas", text="Tortilla\n\n• 6 huevos\n")
    prepared = await t.prepare(params, ctx)
    first = await t.execute(params, ctx, prepared)
    path = tmp_path / NOTES_FOLDER / "Tortilla de patatas (13-11-2026).txt"
    assert first.ok and opened == [path]
    # Saltos de línea de Windows (para el Bloc de notas); los parámetros llegan recortados.
    assert path.read_bytes() == "Tortilla\r\n\r\n• 6 huevos".encode()
    assert prepared.targets == [path]  # SafetyGuard mira dónde se escribe

    # La segunda, con el mismo título, al lado: la primera no se toca.
    second = await t.execute(params, ctx, await t.prepare(params, ctx))
    copy = tmp_path / NOTES_FOLDER / "Tortilla de patatas (13-11-2026) (2).txt"
    assert second.ok and copy.exists() and path.read_text(encoding="utf-8").startswith("Tortilla")

    # Deshacer: a la papelera, nunca borrado permanente.
    trashed: list[list[Path]] = []
    monkeypatch.setattr(save_note, "trash_all", trashed.append)
    assert second.undo is not None
    assert await second.undo.action() == "Nota enviada a la papelera"
    assert trashed == [[copy]]


async def test_created_in_between_is_not_overwritten(tmp_path: Path, ctx: ToolContext) -> None:
    t = tool(tmp_path, [])
    params = SaveNoteParams(title="Lista", text="leche")
    prepared = await t.prepare(params, ctx)
    target: Path = prepared.payload
    await asyncio.to_thread(occupy, target)  # aparece entre preparar y ejecutar
    result = await t.execute(params, ctx, prepared)
    assert not result.ok
    assert await asyncio.to_thread(target.read_text, encoding="utf-8") == "de otro"


def occupy(path: Path) -> None:
    path.parent.mkdir(parents=True)
    path.write_text("de otro", encoding="utf-8")


async def test_without_documents(ctx: ToolContext) -> None:
    prepared = await tool(None, []).prepare(SaveNoteParams(title="x", text="y"), ctx)
    assert prepared.error is not None and not prepared.error.ok
