"""Listas y tareas de Nyx (tarea 8.01): locales, en SQLite, y nunca se borran del todo.

`%LOCALAPPDATA%\\Nyx\\organizer.db`. Quitar un elemento, vaciar una lista o borrar una tarea
solo la marca como borrada (`deleted`): deshacer la recupera, y lo borrado se queda en la base
(la «papelera» de Nyx). Las notas siguen siendo archivos (`save_note`, 6.28).

Las listas se nombran como las dice la gente: «la lista de la compra», «la compra» y «lista
compra» son la misma (`list_key`). Si no se dice cuál, va a «pendientes», la general.
"""

from __future__ import annotations

import re
import sqlite3
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from nyx.index.aliases import normalize, strip_articles
from nyx.paths import local_dir

#: La lista cuando no se dice cuál («apunta pan en la lista»).
DEFAULT_LIST = "pendientes"
MAX_TEXT = 200
MAX_ITEMS = 500

_SCHEMA = """
CREATE TABLE IF NOT EXISTS lists (
    id INTEGER PRIMARY KEY,
    key TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY,
    list_id INTEGER NOT NULL REFERENCES lists(id),
    text TEXT NOT NULL,
    done REAL,
    created REAL NOT NULL,
    deleted REAL
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY,
    text TEXT NOT NULL,
    due REAL,
    alarm_id TEXT,
    done REAL,
    created REAL NOT NULL,
    deleted REAL
);
"""

_LIST_WORDS = re.compile(
    r"^(?:(?:mi|mis|la|las|el|los|una)\s+)?(?:listas?\s+)?(?:(?:de\s+la|de\s+las|de\s+los|del|de)\s+)?"
)


def list_key(name: str) -> str:
    """«La lista de la compra» → «compra»; «mi lista de pendientes» → «pendientes»."""
    key = normalize(name)
    key = _LIST_WORDS.sub("", key).strip()
    return key or DEFAULT_LIST


def split_items(text: str) -> list[str]:
    """«leche, huevos y pan» → ["leche", "huevos", "pan"] (sin repetidos)."""
    # «y», y «e» delante de «i» o «hi» («agua e hielo»).
    parts = re.split(r",|;|\s+y\s+|\s+e\s+(?=[hH]?[iIíÍ])", text)
    out: list[str] = []
    for part in parts:
        clean = " ".join(part.split()).strip(" .")
        # «el pan» → «pan» (sin tocar mayúsculas ni tildes de lo demás).
        clean = re.sub(r"^(?:el|la|los|las|un|una|unos|unas)\s+", "", clean, flags=re.I)[:MAX_TEXT]
        if clean and clean.lower() not in (o.lower() for o in out):
            out.append(clean)
    return out


@dataclass(frozen=True, slots=True)
class Item:
    id: int
    text: str
    done: bool


@dataclass(frozen=True, slots=True)
class Task:
    id: int
    text: str
    due: float | None
    alarm_id: str | None
    done: bool


class OrganizerStore:
    def __init__(self, path: Path, *, clock: Callable[[], float] = time.time) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(_SCHEMA)
        self._clock = clock

    @classmethod
    def default(cls) -> OrganizerStore:
        return cls(local_dir() / "organizer.db")

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def _now(self) -> float:
        return self._clock()

    # --- Listas ---------------------------------------------------------------------------------

    def _list_id(self, name: str, *, create: bool) -> int | None:
        key = list_key(name)
        row = self._db.execute("SELECT id FROM lists WHERE key = ?", (key,)).fetchone()
        if row is not None:
            return int(row[0])
        if not create:
            return None
        cur = self._db.execute(
            "INSERT INTO lists (key, title, created) VALUES (?, ?, ?)", (key, key, self._now())
        )
        return int(cur.lastrowid or 0)

    def lists(self) -> list[tuple[str, int]]:
        """Las listas con algo dentro y cuántos elementos tienen."""
        with self._lock:
            rows = self._db.execute(
                "SELECT l.title, COUNT(i.id) FROM lists l JOIN items i ON i.list_id = l.id "
                "WHERE i.deleted IS NULL GROUP BY l.id ORDER BY l.title"
            ).fetchall()
        return [(str(t), int(n)) for t, n in rows]

    def items(self, name: str) -> list[Item]:
        with self._lock:
            list_id = self._list_id(name, create=False)
            if list_id is None:
                return []
            rows = self._db.execute(
                "SELECT id, text, done FROM items WHERE list_id = ? AND deleted IS NULL "
                "ORDER BY id",
                (list_id,),
            ).fetchall()
        return [Item(int(i), str(t), d is not None) for i, t, d in rows]

    def add_items(self, name: str, texts: Iterable[str]) -> tuple[list[int], list[str]]:
        """Añade lo que no esté ya. Devuelve (ids nuevos, lo que ya estaba)."""
        added: list[int] = []
        already: list[str] = []
        with self._lock:
            list_id = self._list_id(name, create=True)
            current = {
                normalize(str(t)): int(i)
                for i, t in self._db.execute(
                    "SELECT id, text FROM items WHERE list_id = ? AND deleted IS NULL",
                    (list_id,),
                ).fetchall()
            }
            for text in texts:
                text = text.strip()[:MAX_TEXT]
                if not text:
                    continue
                if normalize(text) in current:
                    already.append(text)
                    continue
                if len(current) >= MAX_ITEMS:
                    break
                cur = self._db.execute(
                    "INSERT INTO items (list_id, text, created) VALUES (?, ?, ?)",
                    (list_id, text, self._now()),
                )
                current[normalize(text)] = int(cur.lastrowid or 0)
                added.append(int(cur.lastrowid or 0))
        return added, already

    def find_items(self, name: str, text: str) -> list[Item]:
        """Los elementos que encajan con `text`: igual, o que lo contienen."""
        wanted = strip_articles(normalize(text))
        found = self.items(name)
        exact = [i for i in found if strip_articles(normalize(i.text)) == wanted]
        return exact or [i for i in found if wanted and wanted in normalize(i.text)]

    def remove(self, ids: Iterable[int]) -> list[int]:
        """Marca como borrados (deshacer: `restore`)."""
        ids = list(ids)
        with self._lock:
            self._db.executemany(
                "UPDATE items SET deleted = ? WHERE id = ? AND deleted IS NULL",
                [(self._now(), i) for i in ids],
            )
        return ids

    def restore(self, ids: Iterable[int]) -> None:
        with self._lock:
            self._db.executemany(
                "UPDATE items SET deleted = NULL WHERE id = ?", [(i,) for i in ids]
            )

    def clear(self, name: str) -> list[int]:
        """Vacía la lista (todo a la papelera de Nyx). Devuelve lo quitado, para deshacer."""
        return self.remove(i.id for i in self.items(name))

    def set_done(self, ids: Iterable[int], done: bool) -> None:
        with self._lock:
            self._db.executemany(
                "UPDATE items SET done = ? WHERE id = ?",
                [(self._now() if done else None, i) for i in ids],
            )

    # --- Tareas ---------------------------------------------------------------------------------

    def add_task(self, text: str, due: float | None = None, alarm_id: str | None = None) -> Task:
        text = text.strip()[:MAX_TEXT]
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO tasks (text, due, alarm_id, created) VALUES (?, ?, ?, ?)",
                (text, due, alarm_id, self._now()),
            )
        return Task(int(cur.lastrowid or 0), text, due, alarm_id, False)

    def tasks(self, *, until: float | None = None, done: bool = False) -> list[Task]:
        """Las pendientes (o las hechas), las que tienen fecha primero; con `until`, solo las
        que vencen antes (y las que no tienen fecha)."""
        query = "SELECT id, text, due, alarm_id, done FROM tasks WHERE deleted IS NULL AND " + (
            "done IS NOT NULL" if done else "done IS NULL"
        )
        args: list[object] = []
        if until is not None:
            query += " AND (due IS NULL OR due <= ?)"
            args.append(until)
        query += " ORDER BY due IS NULL, due, id"
        with self._lock:
            rows = self._db.execute(query, args).fetchall()
        return [Task(int(i), str(t), d, a, x is not None) for i, t, d, a, x in rows]

    def find_tasks(self, text: str) -> list[Task]:
        wanted = strip_articles(normalize(text))
        pending = self.tasks()
        exact = [t for t in pending if normalize(t.text) == wanted]
        return exact or [t for t in pending if wanted and wanted in normalize(t.text)]

    def finish_task(self, task_id: int, done: bool = True) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE tasks SET done = ? WHERE id = ?",
                (self._now() if done else None, task_id),
            )

    def delete_task(self, task_id: int, deleted: bool = True) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE tasks SET deleted = ? WHERE id = ?",
                (self._now() if deleted else None, task_id),
            )
