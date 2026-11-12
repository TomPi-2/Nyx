r"""Atajos aprendidos (SPEC sección 6): «el router aprende».

Cuando el LLM resuelve una frase con una sola acción y sale bien, se guarda frase → llamada en
%LOCALAPPDATA%\Nyx\shortcuts.db. La próxima vez esa frase se ejecuta sin LLM (~10 ms en vez de
~0,6 s). Si el usuario deshace la acción justo después, el atajo se olvida.

No se aprende:
- lo rojo (borrar…) ni `undo` / `wait_for_window`;
- lo que depende del momento: «ciérralo», «maximiza esto», o llamadas sin la app (la ventana
  activa de ahora no es la de mañana);
- frases muy largas (no se repiten igual).

En Ajustes se podrán ver y borrar (fase 5): `all()` y `forget()`.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nyx.executor import ToolCall
from nyx.index.aliases import normalize
from nyx.paths import local_dir

MAX_WORDS = 14
# `system_power` es verde solo por «bloquear»; apagar o reiniciar son rojas al prepararlas, y
# aquí solo se ve el riesgo de la herramienta: no se aprende ninguna.
NEVER = {"undo", "wait_for_window", "delete_files", "system_power"}
# Herramientas que, sin app o ventana concreta, actúan sobre «la de ahora».
NEEDS_TARGET = {
    "close_app": ("name",),
    "window_layout": ("name",),
    "focus_window": ("name",),
    "app_action": ("app",),
    "send_hotkey": ("app",),
}
_DEICTIC = {
    "esto",
    "esta",
    "este",
    "eso",
    "esa",
    "ese",
    "aqui",
    "ahi",
    "alli",
    "ahora",
    "anterior",
    "otra",
    "otro",
}
_CLITIC = re.compile(
    r"\b(?:abre|cierra|maximiza|minimiza|mueve|copia|borra|pon|quita|sube|baja|guarda|"
    r"renombra|deja|manda|pasa|silencia|para|cambia)(?:melo|mela|lo|la|los|las|le|les)\b"
)
_POLITE = re.compile(r"\s+(?:por favor|porfa|gracias)$|^(?:oye|venga|vale)\s+")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS shortcuts (
    phrase TEXT PRIMARY KEY,
    tool TEXT NOT NULL,
    arguments TEXT NOT NULL,
    uses INTEGER NOT NULL DEFAULT 0,
    created REAL NOT NULL,
    last_used REAL
);
"""


@dataclass(frozen=True, slots=True)
class Learned:
    phrase: str
    call: ToolCall
    uses: int


def phrase_key(text: str) -> str | None:
    """La frase normalizada, o None si no se debe aprender (depende del contexto, muy larga)."""
    key = _POLITE.sub("", normalize(text)).strip()
    words = key.split()
    if not words or len(words) > MAX_WORDS:
        return None
    if _DEICTIC.intersection(words) or _CLITIC.search(key):
        return None
    return key


def learnable(call: ToolCall, risk: str) -> bool:
    if call.name in NEVER or risk == "red":
        return False
    needed = NEEDS_TARGET.get(call.name, ())
    return all(call.arguments.get(arg) for arg in needed)


class ShortcutStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(_SCHEMA)

    @classmethod
    def default(cls) -> ShortcutStore:
        return cls(local_dir() / "shortcuts.db")

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def lookup(self, text: str) -> ToolCall | None:
        key = phrase_key(text)
        if key is None:
            return None
        with self._lock:
            row = self._db.execute(
                "SELECT tool, arguments FROM shortcuts WHERE phrase = ?", (key,)
            ).fetchone()
            if row is None:
                return None
            self._db.execute(
                "UPDATE shortcuts SET uses = uses + 1, last_used = ? WHERE phrase = ?",
                (time.time(), key),
            )
        arguments: dict[str, Any] = json.loads(row[1])
        return ToolCall(row[0], arguments)

    def learn(self, text: str, call: ToolCall, risk: str) -> str | None:
        """Guarda el atajo si se puede; devuelve la frase normalizada (o None)."""
        key = phrase_key(text)
        if key is None or not learnable(call, risk):
            return None
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO shortcuts (phrase, tool, arguments, uses, created) "
                "VALUES (?, ?, ?, 0, ?)",
                (key, call.name, json.dumps(call.arguments, ensure_ascii=False), time.time()),
            )
        return key

    def forget(self, phrase: str) -> bool:
        with self._lock:
            cur = self._db.execute("DELETE FROM shortcuts WHERE phrase = ?", (phrase,))
        return cur.rowcount > 0

    def forget_all(self) -> int:
        """Olvida todos los atajos aprendidos (Ajustes → Cerebro, 6.24). Devuelve cuántos."""
        with self._lock:
            cur = self._db.execute("DELETE FROM shortcuts")
        return cur.rowcount

    def all(self) -> list[Learned]:
        with self._lock:
            rows = self._db.execute(
                "SELECT phrase, tool, arguments, uses FROM shortcuts ORDER BY uses DESC, phrase"
            ).fetchall()
        return [Learned(r[0], ToolCall(r[1], json.loads(r[2])), r[3]) for r in rows]
