r"""Cuentas del día para los datos de uso anónimos (SPEC §8; 2026-11-16).

Se apunta siempre en local, en `%LOCALAPPDATA%\Nyx\uso\AAAA-MM-DD.json` (aunque el usuario no
haya dado permiso: así «ver qué se envía» enseña algo y nada se envía sin su permiso). Solo
números y nombres de herramientas o de códigos: nunca frases, nombres de apps, rutas ni nada
de lo que pide el usuario (lo de la columna «nunca se envía» de la SPEC).

- `request(path, ms, first_token_ms)`: una petición atendida y por dónde (router, modelo…).
- `activation(verified)`: «Nyx» oído y si se confirmó o era una falsa activación.
- `error(code)`: un código de `docs/CODIGOS-DE-ERROR.md` o un tipo de fallo interno.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from nyx.paths import local_dir

log = logging.getLogger(__name__)

#: Por dónde se atendió una petición.
PATHS = ("router", "llm", "shortcut", "refusal", "setup")
#: Latencias que se guardan por día (las primeras; con eso salen bien la mediana y el p90).
MAX_SAMPLES = 400


def folder() -> Path:
    return local_dir() / "uso"


class UsageStats:
    def __init__(self, root: Path | None = None, *, today: Callable[[], date] = date.today) -> None:
        self.root = root or folder()
        self._today = today
        self._lock = threading.Lock()
        self._day: date | None = None
        self._data: dict[str, Any] = {}

    # --- Lo que se apunta ----------------------------------------------------------------------

    def request(
        self, path: str, ms: float | None = None, first_token_ms: float | None = None
    ) -> None:
        if path not in PATHS:
            return
        with self._lock:
            data = self._load_today()
            data["requests"][path] = data["requests"].get(path, 0) + 1
            if ms is not None and len(data["latency_ms"].setdefault(path, [])) < MAX_SAMPLES:
                data["latency_ms"][path].append(round(ms))
            if first_token_ms is not None and len(data["first_token_ms"]) < MAX_SAMPLES:
                data["first_token_ms"].append(round(first_token_ms))
            self._save()

    def activation(self, verified: bool | None) -> None:
        key = {True: "ok", False: "false", None: "unverified"}[verified]
        with self._lock:
            data = self._load_today()
            data["activations"][key] = data["activations"].get(key, 0) + 1
            self._save()

    def error(self, code: str) -> None:
        code = "".join(c for c in code if c.isalnum() or c in "-_")[:40]
        if not code:
            return
        with self._lock:
            data = self._load_today()
            data["errors"][code] = data["errors"].get(code, 0) + 1
            self._save()

    # --- Lectura -------------------------------------------------------------------------------

    def day(self, which: date) -> dict[str, Any] | None:
        """Lo apuntado ese día (o None si no hay nada)."""
        path = self.root / f"{which:%Y-%m-%d}.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except OSError, ValueError:
            return None
        return data if isinstance(data, dict) else None

    # --- Por dentro ----------------------------------------------------------------------------

    def _load_today(self) -> dict[str, Any]:
        today = self._today()
        if self._day != today:
            self._day = today
            self._data = self.day(today) or {}
            for key in ("requests", "latency_ms", "activations", "errors"):
                self._data.setdefault(key, {})
            self._data.setdefault("first_token_ms", [])
        return self._data

    def _save(self) -> None:
        assert self._day is not None
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            path = self.root / f"{self._day:%Y-%m-%d}.json"
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data, separators=(",", ":")), encoding="utf-8")
            tmp.replace(path)
        except OSError:
            log.debug("No se pudieron guardar los datos de uso", exc_info=True)


#: El de Nyx (uno por proceso); las pruebas crean el suyo.
STATS = UsageStats()
