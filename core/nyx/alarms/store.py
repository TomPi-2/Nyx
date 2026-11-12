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
# Alarmas que se repiten (6.12): ninguna, todos los días, de lunes a viernes o fines de semana.
Repeat = Literal["none", "daily", "weekdays", "weekends"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS alarms (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    due REAL NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    duration_s INTEGER,
    created REAL NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending',  -- pending | fired | cancelled
    repeat TEXT NOT NULL DEFAULT 'none'
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
    repeat: Repeat = "none"


class AlarmStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.executescript(_SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        """Bases creadas antes de la 6.12: sin la columna `repeat` (las guardadas no se tocan)."""
        columns = {row[1] for row in self._db.execute("PRAGMA table_info(alarms)")}
        if "repeat" not in columns:
            self._db.execute("ALTER TABLE alarms ADD COLUMN repeat TEXT NOT NULL DEFAULT 'none'")

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
        repeat: Repeat = "none",
    ) -> Alarm:
        alarm = Alarm(uuid.uuid4().hex[:12], kind, due, label, duration_s, now, repeat)
        with self._lock:
            self._db.execute(
                "INSERT INTO alarms (id, kind, due, label, duration_s, created, repeat) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (alarm.id, kind, due, label, duration_s, now, repeat),
            )
        return alarm

    def pending(self) -> list[Alarm]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, kind, due, label, duration_s, created, repeat FROM alarms "
                "WHERE state = 'pending' ORDER BY due"
            ).fetchall()
        return [Alarm(r[0], r[1], r[2], r[3], r[4], r[5], r[6]) for r in rows]

    def reschedule(self, alarm_id: str, due: float) -> bool:
        """Mueve una alarma que se repite a su siguiente vez (sigue pendiente, mismo id)."""
        with self._lock:
            cur = self._db.execute(
                "UPDATE alarms SET due = ? WHERE id = ? AND state = 'pending'", (due, alarm_id)
            )
        return cur.rowcount > 0

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
