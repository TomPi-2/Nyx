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
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    start REAL NOT NULL,
    minutes INTEGER NOT NULL DEFAULT 60,
    all_day INTEGER NOT NULL DEFAULT 0,
    remind INTEGER,
    repeat TEXT NOT NULL DEFAULT 'none',
    uid TEXT,
    created REAL NOT NULL,
    deleted REAL
);
CREATE INDEX IF NOT EXISTS events_uid ON events(uid);
CREATE TABLE IF NOT EXISTS event_alarms (
    event_id INTEGER NOT NULL REFERENCES events(id),
    occurrence REAL NOT NULL,
    alarm_id TEXT NOT NULL,
    PRIMARY KEY (event_id, occurrence)
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


@dataclass(frozen=True, slots=True)
class Event:
    """Una cita del calendario (8.02). `start` en segundos (hora local del PC); `remind`,
    minutos antes del aviso (None: sin aviso); `repeat`: none, weekly, monthly o yearly."""

    id: int
    title: str
    start: float
    minutes: int
    all_day: bool
    remind: int | None
    repeat: str
    uid: str | None = None


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

    # --- Calendario (8.02) ----------------------------------------------------------------------

    _EVENT_COLS = "id, title, start, minutes, all_day, remind, repeat, uid"

    @staticmethod
    def _event(row: tuple[object, ...]) -> Event:
        i, title, start, minutes, all_day, remind, repeat, uid = row
        return Event(
            int(i),  # type: ignore[call-overload]
            str(title),
            float(start),  # type: ignore[arg-type]
            int(minutes),  # type: ignore[call-overload]
            bool(all_day),
            None if remind is None else int(remind),  # type: ignore[call-overload]
            str(repeat),
            None if uid is None else str(uid),
        )

    def add_event(
        self,
        title: str,
        start: float,
        *,
        minutes: int = 60,
        all_day: bool = False,
        remind: int | None = None,
        repeat: str = "none",
        uid: str | None = None,
    ) -> Event:
        title = title.strip()[:MAX_TEXT]
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO events (title, start, minutes, all_day, remind, repeat, uid, created)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (title, start, minutes, int(all_day), remind, repeat, uid, self._now()),
            )
        return Event(int(cur.lastrowid or 0), title, start, minutes, all_day, remind, repeat, uid)

    def events(self) -> list[Event]:
        """Todas las citas sin borrar (las que se repiten también, una vez)."""
        with self._lock:
            rows = self._db.execute(
                f"SELECT {self._EVENT_COLS} FROM events WHERE deleted IS NULL ORDER BY start"
            ).fetchall()
        return [self._event(r) for r in rows]

    def event(self, event_id: int) -> Event | None:
        with self._lock:
            row = self._db.execute(
                f"SELECT {self._EVENT_COLS} FROM events WHERE id = ?", (event_id,)
            ).fetchone()
        return self._event(row) if row else None

    def has_uid(self, uid: str) -> bool:
        with self._lock:
            row = self._db.execute(
                "SELECT 1 FROM events WHERE uid = ? AND deleted IS NULL", (uid,)
            ).fetchone()
        return row is not None

    def find_events(self, title: str) -> list[Event]:
        """Las citas cuyo título encaja: igual, o que lo contiene («dentista» → «Dentista»)."""
        wanted = strip_articles(normalize(title))
        found = self.events()
        exact = [e for e in found if strip_articles(normalize(e.title)) == wanted]
        return exact or [e for e in found if wanted and wanted in normalize(e.title)]

    def move_event(self, event_id: int, start: float) -> None:
        with self._lock:
            self._db.execute("UPDATE events SET start = ? WHERE id = ?", (start, event_id))

    def delete_event(self, event_id: int, deleted: bool = True) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE events SET deleted = ? WHERE id = ?",
                (self._now() if deleted else None, event_id),
            )

    def event_alarms(self, event_id: int) -> dict[float, str]:
        """Los avisos ya puestos de una cita: {inicio de esa vez: id de la alarma}."""
        with self._lock:
            rows = self._db.execute(
                "SELECT occurrence, alarm_id FROM event_alarms WHERE event_id = ?", (event_id,)
            ).fetchall()
        return {float(o): str(a) for o, a in rows}

    def set_event_alarm(self, event_id: int, occurrence: float, alarm_id: str) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO event_alarms (event_id, occurrence, alarm_id)"
                " VALUES (?, ?, ?)",
                (event_id, occurrence, alarm_id),
            )

    def clear_event_alarms(self, event_id: int) -> list[str]:
        """Olvida los avisos de una cita (al moverla o borrarla). Devuelve sus alarmas."""
        with self._lock:
            rows = self._db.execute(
                "SELECT alarm_id FROM event_alarms WHERE event_id = ?", (event_id,)
            ).fetchall()
            self._db.execute("DELETE FROM event_alarms WHERE event_id = ?", (event_id,))
        return [str(a) for (a,) in rows]
