"""Vigila el menú Inicio, el escritorio, las bibliotecas de Steam y las carpetas del usuario
para reescanear al momento cuando se instala algo o se crea una carpeta (SPEC sección 10).

Los eventos se agrupan (5 s sin cambios) para no reescanear con cada archivo de una instalación.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DEBOUNCE_S = 5.0


class IndexWatcher:
    def __init__(self, on_change: Callable[[], Awaitable[Any]]) -> None:
        self._on_change = on_change
        self._observer: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pending: asyncio.TimerHandle | None = None
        self._task: asyncio.Task[Any] | None = None

    def start(self, recursive: list[Path], shallow: list[Path]) -> None:
        """`recursive`: cualquier cambio cuenta. `shallow`: solo carpetas creadas o borradas."""
        from watchdog.events import FileSystemEvent, FileSystemEventHandler
        from watchdog.observers import Observer

        self._loop = asyncio.get_running_loop()
        watcher = self

        class Handler(FileSystemEventHandler):
            def __init__(self, dirs_only: bool) -> None:
                self.dirs_only = dirs_only

            def on_any_event(self, event: FileSystemEvent) -> None:
                if event.event_type in ("opened", "closed", "closed_no_write", "modified"):
                    return
                if self.dirs_only and not event.is_directory:
                    return
                watcher._schedule()

        observer = Observer()
        for path in recursive:
            if path.exists():
                observer.schedule(Handler(dirs_only=False), str(path), recursive=True)
        for path in shallow:
            if path.exists():
                observer.schedule(Handler(dirs_only=True), str(path), recursive=False)
        observer.daemon = True
        observer.start()
        self._observer = observer

    def _schedule(self) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._debounce)

    def _debounce(self) -> None:
        if self._pending is not None:
            self._pending.cancel()
        assert self._loop is not None
        self._pending = self._loop.call_later(DEBOUNCE_S, self._fire)

    def _fire(self) -> None:
        self._pending = None
        if self._task is None or self._task.done():
            log.info("Cambios en apps o carpetas: reescaneo")
            self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        try:
            await self._on_change()
        except Exception:
            log.warning("Fallo al reescanear", exc_info=True)

    def stop(self) -> None:
        if self._pending is not None:
            self._pending.cancel()
        if self._observer is not None:
            with contextlib.suppress(Exception):
                self._observer.stop()
                self._observer.join(timeout=2)
            self._observer = None
