"""JSON-RPC por la entrada y salida estándar de una extensión con código (tarea 7.06).

Un mensaje por línea, en UTF-8, como JSON-RPC 2.0 sin el campo «jsonrpc»:

    petición       {"id": 1, "method": "call", "params": {...}}
    respuesta      {"id": 1, "result": ...}   o   {"id": 1, "error": {"message": "..."}}
    aviso          {"method": "log", "params": {"text": "..."}}

Las dos partes piden cosas: Nyx pide a la extensión que ejecute una herramienta (`call`) y la
extensión pide a Nyx lo que ella no puede hacer encerrada (leer un archivo, conectar con un
servidor… 7.07), que Nyx hace solo si el permiso está aceptado.

Las tuberías anónimas de Windows no admiten E/S asíncrona, así que un hilo lee y otro escribe;
el bucle de asyncio nunca se bloquea aunque la extensión deje de leer. Lo que no sea un mensaje
válido (una línea enorme, JSON roto, un id que no se ha pedido) cierra la conexión: la
extensión se trata como caída.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import json
import logging
import queue
import threading
from collections.abc import Awaitable, Callable
from typing import IO, Any

log = logging.getLogger(__name__)

#: Tope de una línea (un mensaje). Una extensión que mande más se corta.
MAX_LINE = 1 << 20

Handler = Callable[[dict[str, Any]], Awaitable[Any]]


class RpcError(Exception):
    """La otra parte contestó con un error (la herramienta falló, falta un permiso…)."""


class ConnectionLostError(Exception):
    """La conexión se cerró (la extensión se cayó, se cerró o mandó algo que no vale)."""


class Connection:
    """Una conexión con un proceso: `reader` y `writer` son sus extremos de las tuberías."""

    def __init__(
        self,
        reader: IO[bytes],
        writer: IO[bytes],
        handlers: dict[str, Handler] | None = None,
        *,
        on_close: Callable[[str], None] | None = None,
        name: str = "extensión",
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._handlers = handlers or {}
        self._on_close = on_close
        self._name = name
        self._loop = asyncio.get_running_loop()
        self._ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._out: queue.Queue[bytes | None] = queue.Queue()
        self._tasks: set[asyncio.Task[None]] = set()
        self.closed: str | None = None  # el motivo, cuando se cierra
        threading.Thread(target=self._read_loop, name=f"rpc-in {name}", daemon=True).start()
        threading.Thread(target=self._write_loop, name=f"rpc-out {name}", daemon=True).start()

    # --- Lo que usa Nyx -----------------------------------------------------------------------

    async def request(self, method: str, params: dict[str, Any], timeout_s: float) -> Any:
        """Pide algo y espera la respuesta. Lanza RpcError, ConnectionLostError o TimeoutError."""
        if self.closed:
            raise ConnectionLostError(self.closed)
        msg_id = next(self._ids)
        future: asyncio.Future[Any] = self._loop.create_future()
        self._pending[msg_id] = future
        self._send({"id": msg_id, "method": method, "params": params})
        try:
            return await asyncio.wait_for(future, timeout_s)
        finally:
            self._pending.pop(msg_id, None)

    def notify(self, method: str, params: dict[str, Any]) -> None:
        if not self.closed:
            self._send({"method": method, "params": params})

    def close(self, reason: str = "cerrada por Nyx") -> None:
        if self.closed:
            return
        self.closed = reason
        self._out.put(None)
        for future in self._pending.values():
            if not future.done():
                future.set_exception(ConnectionLostError(reason))
        self._pending.clear()
        for task in self._tasks:
            task.cancel()
        # La tubería de lectura no se cierra aquí: el hilo que lee la tiene bloqueada y cerrarla
        # esperaría a que acabe. Al matar el proceso llega el final y el hilo sale solo.
        if self._on_close:
            self._on_close(reason)

    # --- Hilos ----------------------------------------------------------------------------------

    def _send(self, message: dict[str, Any]) -> None:
        data = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._out.put(data + b"\n")

    def _write_loop(self) -> None:
        while (data := self._out.get()) is not None:
            try:
                self._writer.write(data)
                self._writer.flush()
            except (OSError, ValueError):
                self._loop.call_soon_threadsafe(self.close, "la extensión dejó de leer")
                break
        with contextlib.suppress(OSError, ValueError):
            self._writer.close()

    def _read_loop(self) -> None:
        reason = "la extensión se cerró"
        try:
            while True:
                line = self._reader.readline(MAX_LINE + 1)
                if not line:
                    break
                if len(line) > MAX_LINE:
                    reason = "mensaje demasiado largo"
                    break
                if not line.strip():
                    continue
                try:
                    message = json.loads(line)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    reason = "mensaje que no es JSON"
                    break
                if not isinstance(message, dict):
                    reason = "mensaje que no es un objeto"
                    break
                self._loop.call_soon_threadsafe(self._dispatch, message)
        except (OSError, ValueError):
            pass
        with contextlib.suppress(RuntimeError):  # el bucle ya se cerró
            self._loop.call_soon_threadsafe(self.close, reason)

    # --- Mensajes que llegan --------------------------------------------------------------------

    def _dispatch(self, message: dict[str, Any]) -> None:
        if self.closed:
            return
        method = message.get("method")
        if isinstance(method, str):
            params = message.get("params", {})
            if not isinstance(params, dict):
                return self.close("parámetros que no son un objeto")
            task = self._loop.create_task(self._answer(message.get("id"), method, params))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            return
        msg_id = message.get("id")
        future = self._pending.get(msg_id) if isinstance(msg_id, int) else None
        if future is None:
            return self.close("respuesta a algo que no se ha pedido")
        if future.done():
            return
        if "error" in message:
            error = message["error"]
            text = error.get("message") if isinstance(error, dict) else None
            future.set_exception(RpcError(str(text or "error sin explicación")[:500]))
        else:
            future.set_result(message.get("result"))

    async def _answer(self, msg_id: Any, method: str, params: dict[str, Any]) -> None:
        handler = self._handlers.get(method)
        reply: dict[str, Any]
        try:
            if handler is None:
                raise RpcError(f"Nyx no conoce «{method[:60]}»")
            reply = {"result": await handler(params)}
        except RpcError as e:
            reply = {"error": {"message": str(e)}}
        except Exception:
            log.exception("%s: fallo al atender «%s»", self._name, method)
            reply = {"error": {"message": "fallo interno de Nyx"}}
        if msg_id is not None:  # los avisos no se contestan
            self._send({"id": msg_id, **reply})
