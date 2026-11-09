r"""Registro de acciones (SPEC sección 8): fecha, frase, herramienta, parámetros, decisión y
resultado de cada acción, en %LOCALAPPDATA%\Nyx\actions\AAAA-MM-DD.jsonl.

Es local; se borra lo de más de 30 días. Lo consultará la ventana de Ajustes (fase 5).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

from nyx.log import request_id
from nyx.paths import local_dir

log = logging.getLogger(__name__)

KEEP_DAYS = 30


class Decision(StrEnum):
    EXECUTED = "executed"  # verde o amarillo: sin preguntar
    CONFIRMED = "confirmed"  # rojo: el usuario dijo que sí
    CANCELLED = "cancelled"  # rojo: dijo que no o caducó
    BLOCKED = "blocked"  # SafetyGuard no lo permite
    INVALID = "invalid"  # herramienta o parámetros no válidos
    UNDONE = "undone"


@dataclass
class ActionLog:
    folder: Path

    @classmethod
    def default(cls) -> ActionLog:
        log_ = cls(local_dir() / "actions")
        log_.prune()
        return log_

    def write(
        self,
        *,
        tool: str,
        params: dict[str, Any],
        decision: Decision,
        ok: bool | None = None,
        message: str = "",
        phrase: str = "",
        risk: str = "",
    ) -> None:
        now = datetime.now()
        record = {
            "time": now.isoformat(timespec="seconds"),
            "request": request_id.get(),
            "phrase": phrase,
            "tool": tool,
            "params": params,
            "risk": risk,
            "decision": decision.value,
            "ok": ok,
            "message": message,
        }
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            path = self.folder / f"{now:%Y-%m-%d}.jsonl"
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except OSError:
            log.warning("No se pudo escribir el registro de acciones", exc_info=True)

    def prune(self, today: date | None = None) -> None:
        limit = (today or date.today()) - timedelta(days=KEEP_DAYS)
        if not self.folder.exists():
            return
        for path in self.folder.glob("*.jsonl"):
            try:
                if date.fromisoformat(path.stem) < limit:
                    path.unlink()
            except (ValueError, OSError):
                continue

    def read(self, day: date | None = None) -> list[dict[str, Any]]:
        path = self.folder / f"{(day or date.today()):%Y-%m-%d}.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
