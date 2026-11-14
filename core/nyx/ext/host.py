"""Host de extensiones con código (tarea 7.06; HOJA-DE-RUTA §4.4).

Un proceso por extensión, encerrado (sandbox.py), que se arranca la primera vez que hace falta
y se para tras un rato sin uso. Nyx le habla por su entrada y salida estándar (rpc.py):

- **Cada llamada tiene tiempo máximo** (como `Tool.timeout_s`). Si no contesta, se mata: una
  extensión colgada no deja a Nyx esperando.
- **Si se cae, se reinicia** en la siguiente llamada. La llamada que estaba en marcha falla (no
  se repite: podría tener efectos).
- **Tres caídas seguidas** (cerrarse sola, colgarse o mandar algo que no vale) y se desactiva:
  `on_disabled` lo apunta en el gestor y avisa al usuario. Una llamada que va bien pone la
  cuenta a cero; que la herramienta dé un error suyo no es una caída.
- **En partida** las que estén en marcha bajan a la CPU mínima y prioridad «inactiva».

Lo que la extensión pide a Nyx (`handlers`: leer un archivo, conectar con OBS…) lo pone la 7.07
con sus comprobaciones de permisos. Aquí solo se atienden `log` y `fatal`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any, Protocol

from nyx.ext.rpc import Connection, ConnectionLostError, Handler, RpcError

log = logging.getLogger(__name__)

#: Caídas seguidas antes de desactivarla.
MAX_CRASHES = 3
#: Lo que puede tardar en arrancar y presentarse (Python, sus imports y `hello`).
START_TIMEOUT_S = 15.0
#: Sin llamadas durante este tiempo, se para (vuelve a arrancar en 0,1 s si hace falta).
IDLE_STOP_S = 600.0


class Process(Protocol):
    """Un proceso de extensión en marcha (SandboxProcess; en las pruebas, uno sin encerrar)."""

    pid: int
    stdin: IO[bytes]
    stdout: IO[bytes]

    def poll(self) -> int | None: ...
    def wait(self, timeout: float) -> int | None: ...
    def set_game(self, active: bool) -> None: ...
    def kill(self) -> None: ...


class Launcher(Protocol):
    game: bool

    def start(self, ext_id: str, package: Path) -> Process: ...


class ExtensionCrashError(Exception):
    """La extensión se cayó, se colgó o está desactivada por caerse demasiado."""


@dataclass
class _Running:
    process: Process
    conn: Connection
    tools: tuple[str, ...]
    last_used: float = field(default_factory=time.monotonic)
    stopping: bool = False


class ExtensionHost:
    def __init__(
        self,
        launcher: Launcher,
        *,
        on_disabled: Callable[[str, str], Awaitable[None]] | None = None,
        handlers: Callable[[str], dict[str, Handler]] | None = None,
        max_crashes: int = MAX_CRASHES,
        start_timeout: float = START_TIMEOUT_S,
        idle_stop: float = IDLE_STOP_S,
    ) -> None:
        self._launcher = launcher
        self._on_disabled = on_disabled
        self._handlers = handlers
        self._max_crashes = max_crashes
        self._start_timeout = start_timeout
        self._idle_stop = idle_stop
        self._running: dict[str, _Running] = {}
        self._starting: dict[str, asyncio.Lock] = {}
        self.crashes: dict[str, int] = {}
        self.disabled: dict[str, str] = {}  # id → motivo
        self.logs: dict[str, list[str]] = {}  # lo último que ha escrito cada una
        self._reaper: asyncio.Task[None] | None = None

    # --- Lo que usa Nyx -------------------------------------------------------------------------

    async def call(
        self, ext_id: str, package: Path, tool: str, args: dict[str, Any], timeout_s: float
    ) -> Any:
        """Ejecuta una herramienta de la extensión y devuelve lo que conteste.

        Lanza RpcError si la herramienta falla (error suyo) y ExtensionCrashError si la extensión
        se cae, se cuelga o está desactivada.
        """
        if ext_id in self.disabled:
            raise ExtensionCrashError(self.disabled[ext_id])
        running = await self._ensure(ext_id, package)
        running.last_used = time.monotonic()
        try:
            result = await running.conn.request("call", {"tool": tool, "args": args}, timeout_s)
        except TimeoutError:
            await self._crashed(ext_id, running, f"«{tool}» no contestó en {timeout_s:g} s")
            raise ExtensionCrashError(f"«{tool}» tardó demasiado") from None
        except ConnectionLostError as e:
            await self._crashed(ext_id, running, str(e))
            raise ExtensionCrashError(str(e)) from None
        self.crashes.pop(ext_id, None)
        return result

    def tools(self, ext_id: str) -> tuple[str, ...]:
        """Las herramientas que dijo tener al presentarse (si está en marcha)."""
        running = self._running.get(ext_id)
        return running.tools if running else ()

    def enable(self, ext_id: str) -> None:
        """El usuario la vuelve a activar: la cuenta de caídas empieza de cero."""
        self.disabled.pop(ext_id, None)
        self.crashes.pop(ext_id, None)

    def set_game(self, active: bool) -> None:
        self._launcher.game = active
        for ext_id, running in self._running.items():
            try:
                running.process.set_game(active)
            except OSError:
                log.warning("Extensión %s: no se pudo cambiar a modo partida", ext_id)

    async def stop(self, ext_id: str) -> None:
        running = self._running.pop(ext_id, None)
        if running is not None:
            await self._stop(ext_id, running)

    async def stop_all(self) -> None:
        if self._reaper is not None:
            self._reaper.cancel()
            self._reaper = None
        await asyncio.gather(*(self.stop(ext_id) for ext_id in list(self._running)))

    # --- Arrancar y parar -----------------------------------------------------------------------

    async def _ensure(self, ext_id: str, package: Path) -> _Running:
        lock = self._starting.setdefault(ext_id, asyncio.Lock())
        async with lock:
            running = self._running.get(ext_id)
            if running is not None and not running.conn.closed:
                return running
            if running is not None:  # se cayó sin estar haciendo nada: también cuenta
                await self._crashed(ext_id, running, running.conn.closed or "se cerró")
            if ext_id in self.disabled:
                raise ExtensionCrashError(self.disabled[ext_id])
            try:
                running = await self._start(ext_id, package)
            except ExtensionCrashError as e:
                await self._count(ext_id, str(e))
                raise
            self._running[ext_id] = running
            if self._reaper is None and self._idle_stop > 0:
                self._reaper = asyncio.create_task(self._reap_idle())
            return running

    async def _start(self, ext_id: str, package: Path) -> _Running:
        started = time.perf_counter()
        try:
            process = await asyncio.to_thread(self._launcher.start, ext_id, package)
        except OSError as e:
            log.warning("Extensión %s: no arranca", ext_id, exc_info=True)
            raise ExtensionCrashError(f"no arranca: {e}") from None
        handlers: dict[str, Handler] = dict(self._handlers(ext_id)) if self._handlers else {}
        fatal: list[str] = []
        handlers["log"] = self._log_handler(ext_id)
        handlers["fatal"] = self._fatal_handler(ext_id, fatal)
        conn = Connection(process.stdout, process.stdin, handlers, name=ext_id)
        try:
            hello = await conn.request("hello", {"api": "1.0"}, self._start_timeout)
        except (TimeoutError, ConnectionLostError, RpcError) as e:
            conn.close()
            await asyncio.to_thread(process.kill)
            reason = fatal[0] if fatal else f"no se presentó ({type(e).__name__}: {e})"
            raise ExtensionCrashError(reason) from None
        tools = hello.get("tools", []) if isinstance(hello, dict) else []
        names = tuple(t for t in tools if isinstance(t, str))[:200]
        log.info(
            "Extensión %s lista en %.0f ms (%d herramientas)",
            ext_id,
            (time.perf_counter() - started) * 1000,
            len(names),
        )
        return _Running(process, conn, names)

    async def _stop(self, ext_id: str, running: _Running) -> None:
        running.stopping = True
        running.conn.close("parada por Nyx")
        # Se le da un momento para salir sola (su entrada se ha cerrado) y si no, se mata.
        with contextlib.suppress(OSError):
            await asyncio.to_thread(running.process.wait, 1.0)
        await asyncio.to_thread(running.process.kill)
        log.info("Extensión %s parada", ext_id)

    async def _crashed(self, ext_id: str, running: _Running, reason: str) -> None:
        if self._running.get(ext_id) is running:
            del self._running[ext_id]
        if running.stopping:
            return
        log.warning("Extensión %s caída: %s", ext_id, reason)
        await self._stop(ext_id, running)
        await self._count(ext_id, reason)

    async def _count(self, ext_id: str, reason: str) -> None:
        count = self.crashes.get(ext_id, 0) + 1
        self.crashes[ext_id] = count
        if count < self._max_crashes:
            return
        message = f"se ha caído {count} veces seguidas ({reason})"
        self.disabled[ext_id] = message
        log.warning("Extensión %s desactivada: %s", ext_id, message)
        if self._on_disabled is not None:
            await self._on_disabled(ext_id, message)

    async def _reap_idle(self) -> None:
        while self._running:
            await asyncio.sleep(min(60.0, self._idle_stop / 2))
            now = time.monotonic()
            for ext_id, running in list(self._running.items()):
                if running.conn.closed:
                    await self._crashed(ext_id, running, running.conn.closed)
                elif now - running.last_used > self._idle_stop:
                    self._running.pop(ext_id, None)
                    await self._stop(ext_id, running)
        self._reaper = None

    # --- Lo que manda la extensión ----------------------------------------------------------------

    def _log_handler(self, ext_id: str) -> Handler:
        async def handle(params: dict[str, Any]) -> None:
            text = str(params.get("text", ""))[:2000]
            lines = self.logs.setdefault(ext_id, [])
            lines.append(text)
            del lines[:-50]
            level = logging.WARNING if params.get("level") == "error" else logging.INFO
            log.log(level, "[%s] %s", ext_id, text)

        return handle

    def _fatal_handler(self, ext_id: str, out: list[str]) -> Handler:
        async def handle(params: dict[str, Any]) -> None:
            out.append(f"no carga: {str(params.get('text', ''))[:300]}")

        return handle
