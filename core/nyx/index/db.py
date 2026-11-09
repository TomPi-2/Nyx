r"""Caché en SQLite (%LOCALAPPDATA%\Nyx\cache\index.db).

Las entradas se sustituyen enteras en cada escaneo; el uso y los alias del usuario van en
tablas aparte por `key`, así que sobreviven a los reescaneos.
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterable
from pathlib import Path

from nyx.index.model import Entry, Kind, Launch

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    key TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    launch TEXT NOT NULL,
    source TEXT NOT NULL,
    process TEXT,
    aliases TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS usage (
    key TEXT PRIMARY KEY,
    uses INTEGER NOT NULL DEFAULT 0,
    last_used REAL
);
CREATE TABLE IF NOT EXISTS user_aliases (
    alias TEXT PRIMARY KEY,
    key TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    name TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class IndexDB:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Se usa desde el bucle y desde el hilo del escaneo, nunca a la vez (ver service.py).
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.executescript(SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def replace_entries(self, entries: Iterable[Entry]) -> None:
        rows = [
            (
                e.key,
                e.kind.value,
                e.name,
                e.launch.to_json(),
                e.source,
                e.process,
                json.dumps(list(e.aliases), ensure_ascii=False),
            )
            for e in entries
        ]
        with self._conn:
            self._conn.execute("DELETE FROM entries")
            self._conn.executemany("INSERT OR REPLACE INTO entries VALUES (?,?,?,?,?,?,?)", rows)
            self._conn.execute(
                "INSERT OR REPLACE INTO meta VALUES ('last_scan', ?)", (str(time.time()),)
            )

    def entries(self) -> list[Entry]:
        rows = self._conn.execute(
            "SELECT key, kind, name, launch, source, process, aliases FROM entries"
        ).fetchall()
        return [
            Entry(
                key=key,
                kind=Kind(kind),
                name=name,
                launch=Launch.from_json(launch),
                source=source,
                process=process,
                aliases=tuple(json.loads(aliases)),
            )
            for key, kind, name, launch, source, process, aliases in rows
        ]

    def last_scan(self) -> float | None:
        row = self._conn.execute("SELECT value FROM meta WHERE name = 'last_scan'").fetchone()
        return float(row[0]) if row else None

    def usage(self) -> dict[str, int]:
        return dict(self._conn.execute("SELECT key, uses FROM usage").fetchall())

    def record_use(self, key: str, when: float) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO usage (key, uses, last_used) VALUES (?, 1, ?) "
                "ON CONFLICT(key) DO UPDATE SET uses = uses + 1, last_used = excluded.last_used",
                (key, when),
            )

    def user_aliases(self) -> dict[str, str]:
        return dict(self._conn.execute("SELECT alias, key FROM user_aliases").fetchall())

    def set_user_alias(self, alias: str, key: str) -> None:
        with self._conn:
            self._conn.execute("INSERT OR REPLACE INTO user_aliases VALUES (?, ?)", (alias, key))
