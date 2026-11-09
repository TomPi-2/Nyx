r"""Alarmas y temporizadores persistidos en SQLite (%LOCALAPPDATA%\Nyx\alarms.db).

WAL con `synchronous=FULL` (SPEC sección 14): una alarma confirmada sobrevive a un corte de luz.
Las horas se guardan como marca de tiempo (segundos desde 1970), así los cambios de hora de
verano no la mueven.
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from nyx.paths import local_dir

Kind = Literal["alarm", "timer"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS alarms (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    due REAL NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    duration_s INTEGER,
    created REAL NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending'  -- pending | fired | cancelled
);
CREATE INDEX IF NOT EXISTS alarms_pending ON alarms (state, due);
"""


@dataclass(frozen=True, slots=True)
class Alarm:
    id: str
    kind: Kind
    due: float  # marca de tiempo
    label: str = ""
    duration_s: int | None = None  # temporizadores: lo que se pidió («5 min»)
    created: float = 0.0


class AlarmStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.executescript(_SCHEMA)

    @classmethod
    def default(cls) -> AlarmStore:
        return cls(local_dir() / "alarms.db")

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def add(
        self,
        kind: Kind,
        due: float,
        *,
        label: str = "",
        duration_s: int | None = None,
        now: float = 0.0,
    ) -> Alarm:
        alarm = Alarm(uuid.uuid4().hex[:12], kind, due, label, duration_s, now)
        with self._lock:
            self._db.execute(
                "INSERT INTO alarms (id, kind, due, label, duration_s, created) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (alarm.id, kind, due, label, duration_s, now),
            )
        return alarm

    def pending(self) -> list[Alarm]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, kind, due, label, duration_s, created FROM alarms "
                "WHERE state = 'pending' ORDER BY due"
            ).fetchall()
        return [Alarm(r[0], r[1], r[2], r[3], r[4], r[5]) for r in rows]

    def _set_state(self, alarm_id: str, state: str) -> bool:
        with self._lock:
            cur = self._db.execute(
                "UPDATE alarms SET state = ? WHERE id = ? AND state = 'pending'",
                (state, alarm_id),
            )
        return cur.rowcount > 0

    def mark_fired(self, alarm_id: str) -> bool:
        return self._set_state(alarm_id, "fired")

    def cancel(self, alarm_id: str) -> bool:
        return self._set_state(alarm_id, "cancelled")
