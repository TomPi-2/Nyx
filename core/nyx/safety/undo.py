"""Deshacer (SPEC sección 8): las acciones amarillas se pueden revertir durante 30 s,
con el botón de la burbuja o diciendo «Nyx, deshaz»."""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

UNDO_TTL_S = 30.0

# Revierte la acción y devuelve una frase corta de lo que ha hecho.
UndoFn = Callable[[], Awaitable[str]]


@dataclass(frozen=True, slots=True)
class Undo:
    """Lo que devuelve una herramienta amarilla para poder revertirse."""

    summary: str  # «Mover 5 archivos a Documentos»
    action: UndoFn


@dataclass(frozen=True, slots=True)
class UndoEntry:
    id: str
    summary: str
    action: UndoFn
    expires: float


@dataclass
class UndoStack:
    ttl_s: float = UNDO_TTL_S
    clock: Callable[[], float] = time.monotonic
    _entries: list[UndoEntry] = field(default_factory=list)

    def push(self, undo: Undo) -> UndoEntry:
        entry = UndoEntry(
            uuid.uuid4().hex[:12], undo.summary, undo.action, self.clock() + self.ttl_s
        )
        self._entries.append(entry)
        return entry

    def _alive(self) -> list[UndoEntry]:
        now = self.clock()
        self._entries = [e for e in self._entries if e.expires > now]
        return self._entries

    def latest(self) -> UndoEntry | None:
        alive = self._alive()
        return alive[-1] if alive else None

    def take(self, entry_id: str | None = None) -> UndoEntry | None:
        """Saca la entrada (la última si no se dice cuál) para ejecutarla una sola vez."""
        alive = self._alive()
        entry = (
            next((e for e in alive if e.id == entry_id), None)
            if entry_id
            else (alive[-1] if alive else None)
        )
        if entry is not None:
            self._entries.remove(entry)
        return entry
