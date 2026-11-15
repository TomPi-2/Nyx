"""save_note: guarda un texto en una nota nueva y la abre en el Bloc de notas (6.28).

- Siempre en `Documentos\\Notas de Nyx\\` (la carpeta Documentos de verdad, también si está en
  OneDrive), con el nombre «<título> (dd-mm-aaaa).txt». **Nunca sobrescribe**: si ya existe,
  «(2)», «(3)»… y el archivo se crea en modo exclusivo.
- Amarilla: «Deshacer» manda la nota a la papelera (nunca borrado permanente).
- En partida, diferida: no abre el Bloc de notas encima del juego.
- Es lo que usan los botones y las órdenes por voz del panel largo («guárdamela en una nota»),
  y el modelo para «apunta en una nota que mañana tengo dentista».
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import subprocess
from collections.abc import Callable
from datetime import date
from pathlib import Path

from pydantic import Field

from nyx.safety.undo import Undo
from nyx.tools.base import (
    Category,
    GamePolicy,
    Params,
    Prepared,
    Risk,
    Tool,
    ToolContext,
    ToolResult,
)
from nyx.tools.delete_files import trash_all

NOTES_FOLDER = "Notas de Nyx"
MAX_TITLE = 60
MAX_COPIES = 99
_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"con", "prn", "aux", "nul"} | {f"{d}{i}" for d in ("com", "lpt") for i in range(1, 10)}


class SaveNoteParams(Params):
    # Descripciones mínimas: cada carácter del esquema va en el prompt (caben todas las
    # herramientas en su parte del contexto por poco, ver tests/test_select.py).
    title: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=20000)


def file_stem(title: str, today: date) -> str:
    """«Tortilla de patatas (13-11-2026)»: sin caracteres que Windows no admite."""
    clean = " ".join(_INVALID.sub(" ", title).split()).strip(". ")[:MAX_TITLE].rstrip(". ")
    if not clean or clean.lower() in _RESERVED:
        clean = "Nota"
    return f"{clean} ({today:%d-%m-%Y})"


def free_path(folder: Path, stem: str) -> Path | None:
    """El primer nombre libre: «x.txt», «x (2).txt»…; None si están todos cogidos."""
    for n in range(1, MAX_COPIES + 1):
        path = folder / (f"{stem}.txt" if n == 1 else f"{stem} ({n}).txt")
        if not path.exists():
            return path
    return None


def documents_folder() -> Path | None:
    from nyx.index.scanners.folders import known_folders

    return known_folders().get("Documentos")


def open_in_notepad(path: Path) -> None:
    # En la carpeta de la nota: nunca la de Nyx (no dejaría reinstalarla, I-110).
    subprocess.Popen(["notepad.exe", str(path)], close_fds=True, cwd=path.parent)


class SaveNote(Tool[SaveNoteParams]):
    name = "save_note"
    # Sin ejemplo (no cabría): «apunta en una nota que…» lo resuelve el router (router/notas.py).
    description = "Guarda un texto en una nota nueva."
    risk = Risk.YELLOW
    game_policy = GamePolicy.DEFERRED
    category = Category.FILES
    params_model = SaveNoteParams

    def __init__(
        self,
        documents: Callable[[], Path | None] = documents_folder,
        opener: Callable[[Path], None] = open_in_notepad,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._documents = documents
        self._open = opener
        self._today = today

    async def prepare(self, params: SaveNoteParams, ctx: ToolContext) -> Prepared:
        docs = await asyncio.to_thread(self._documents)
        if docs is None:
            return Prepared("", error=ToolResult.fail("No encuentro tu carpeta Documentos"))
        folder = docs / NOTES_FOLDER
        stem = file_stem(params.title, self._today())
        path = await asyncio.to_thread(free_path, folder, stem)
        if path is None:
            return Prepared("", error=ToolResult.fail("Ya hay demasiadas notas con ese nombre"))
        return Prepared(f"Guardar la nota {path.stem}", targets=[path], payload=path)

    async def execute(
        self, params: SaveNoteParams, ctx: ToolContext, prepared: Prepared
    ) -> ToolResult:
        path: Path = prepared.payload
        text = params.text.replace("\r\n", "\n").replace("\n", "\r\n")

        def write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            # «x»: si alguien la ha creado entre medias, falla en vez de sobrescribirla.
            with path.open("x", encoding="utf-8", newline="") as f:
                f.write(text)

        try:
            await asyncio.to_thread(write)
        except FileExistsError:
            return ToolResult.fail("Ya existe una nota con ese nombre", "no la sobrescribo")
        except OSError as e:
            return ToolResult.fail("No he podido guardar la nota", str(e))
        # Si no se abre, la nota está guardada igualmente: se dice dónde está.
        with contextlib.suppress(OSError):
            await asyncio.to_thread(self._open, path)

        async def undo() -> str:
            await asyncio.to_thread(trash_all, [path])
            return "Nota enviada a la papelera"

        return ToolResult(
            ok=True,
            message=f"He guardado la nota {path.stem} en Documentos, {NOTES_FOLDER}.",
            display="Nota guardada",
            secondary=f"Documentos › {NOTES_FOLDER}",
            data={"path": str(path)},
            undo=Undo(prepared.summary, undo),
        )
