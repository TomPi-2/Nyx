r"""Registro con rotación en %LOCALAPPDATA%\Nyx\logs y un ID por petición.

La salida de consola va a stderr: stdout está reservado para los mensajes que lee
el proceso principal (Tauri).
"""

from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from pathlib import Path

request_id: ContextVar[str] = ContextVar("request_id", default="-")

FORMAT = "%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s"


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id.get()
        return True


def new_request_id() -> str:
    """Asigna un ID corto a la petición en curso (se hereda en sus tareas)."""
    rid = uuid.uuid4().hex[:8]
    request_id.set(rid)
    return rid


def setup_logging(level: str = "INFO", log_dir: Path | None = None) -> None:
    # La consola de Windows usa cp1252 por defecto; Tauri lee stderr como UTF-8.
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                log_dir / "core.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
            )
        )
    for handler in handlers:
        handler.addFilter(_RequestIdFilter())
        handler.setFormatter(logging.Formatter(FORMAT))
    logging.basicConfig(level=level, handlers=handlers, force=True)
