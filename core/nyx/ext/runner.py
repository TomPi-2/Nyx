# SPDX-License-Identifier: GPL-3.0-only OR MIT
# También con licencia MIT, como el kit de extensiones (decisión del 2026-11-14).
"""Lo que corre dentro del encierro de cada extensión con código (tarea 7.06).

Nyx lo copia junto al Python de las extensiones y lo lanza así, dentro de un AppContainer sin
capacidades, en un escritorio aparte y con límites de memoria y procesador:

    python.exe -I -X utf8 nyx_runner.py <carpeta del paquete> <carpeta de datos>

Solo usa la biblioteca estándar. Carga `tools/main.py` del paquete (con `tools/lib` para sus
dependencias) y habla con Nyx por la entrada y salida estándar, un JSON por línea (rpc.py).
La extensión ve un módulo `nyx`:

    import nyx

    @nyx.tool
    def saluda(nombre: str) -> str:
        return f"Hola, {nombre}"

    @nyx.tool
    async def escena(nombre: str) -> dict:
        datos = await nyx.ask("net.request", {...})   # lo hace Nyx, si hay permiso (7.07)
        ...

`print` y los errores no rompen el protocolo: van al registro de Nyx como avisos «log».
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import io
import json
import sys
import threading
import traceback
import types
from collections.abc import Callable
from pathlib import Path
from typing import IO, Any

API = "1.0"
MAX_LINE = 1 << 20

_proto_out: IO[bytes] | None = None  # la salida estándar de verdad (main)
_write_lock = threading.Lock()
_loop: asyncio.AbstractEventLoop | None = None
_pending: dict[int, asyncio.Future[Any]] = {}
_next_id = 0
_tools: dict[str, Callable[..., Any]] = {}


def _send(message: dict[str, Any]) -> None:
    data = json.dumps(message, ensure_ascii=False, separators=(",", ":"), default=str)
    raw = data.encode("utf-8") + b"\n"
    if len(raw) > MAX_LINE:
        raw = (
            json.dumps(
                {"id": message.get("id"), "error": {"message": "respuesta demasiado larga"}}
            ).encode("utf-8")
            + b"\n"
        )
    assert _proto_out is not None
    with _write_lock:
        _proto_out.write(raw)
        _proto_out.flush()


class _Log(io.TextIOBase):
    """`print` y `sys.stderr` de la extensión: al registro de Nyx, nunca al protocolo."""

    def __init__(self, level: str) -> None:
        self._level = level
        self._buf = ""

    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip():
                _send({"method": "log", "params": {"level": self._level, "text": line[:2000]}})
        return len(text)


# --- El módulo «nyx» que ve la extensión ------------------------------------------------------


def tool(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Marca una función como herramienta. Su nombre es el de la función."""
    _tools[fn.__name__] = fn
    return fn


async def ask(method: str, params: dict[str, Any] | None = None, timeout_s: float = 30.0) -> Any:
    """Pide algo a Nyx desde una herramienta asíncrona. Lanza RuntimeError si Nyx dice que no."""
    global _next_id
    assert _loop is not None
    _next_id += 1
    msg_id = _next_id
    future: asyncio.Future[Any] = _loop.create_future()
    _pending[msg_id] = future
    _send({"id": msg_id, "method": method, "params": params or {}})
    try:
        return await asyncio.wait_for(future, timeout_s)
    finally:
        _pending.pop(msg_id, None)


def ask_sync(method: str, params: dict[str, Any] | None = None, timeout_s: float = 30.0) -> Any:
    """Lo mismo desde una herramienta normal (no asíncrona), que corre en otro hilo."""
    assert _loop is not None
    return asyncio.run_coroutine_threadsafe(ask(method, params, timeout_s), _loop).result()


def _make_module(data_dir: Path) -> types.ModuleType:
    module = types.ModuleType("nyx", "API de Nyx para extensiones")
    module.tool = tool  # type: ignore[attr-defined]
    module.ask = ask  # type: ignore[attr-defined]
    module.ask_sync = ask_sync  # type: ignore[attr-defined]
    module.API = API  # type: ignore[attr-defined]
    module.data_dir = data_dir  # type: ignore[attr-defined]
    return module


# --- Lo que pide Nyx ----------------------------------------------------------------------------


async def _call(params: dict[str, Any]) -> Any:
    name = params.get("tool")
    args = params.get("args") or {}
    fn = _tools.get(name) if isinstance(name, str) else None
    if fn is None:
        raise LookupError(f"la extensión no tiene la herramienta «{name}»")
    if not isinstance(args, dict):
        raise TypeError("los argumentos no son un objeto")
    if inspect.iscoroutinefunction(fn):
        return await fn(**args)
    return await asyncio.to_thread(fn, **args)


async def _handle(message: dict[str, Any]) -> None:
    msg_id = message.get("id")
    method = message.get("method")
    try:
        if method == "hello":
            result: Any = {"api": API, "tools": sorted(_tools)}
        elif method == "call":
            result = await _call(message.get("params") or {})
        elif method == "ping":
            result = "pong"
        else:
            raise LookupError(f"no sé hacer «{method}»")
        reply: dict[str, Any] = {"id": msg_id, "result": result}
    except Exception as e:
        print("".join(traceback.format_exception(e)), file=sys.stderr)
        reply = {"id": msg_id, "error": {"message": f"{type(e).__name__}: {e}"[:500]}}
    if msg_id is not None:
        _send(reply)


def _reader(loop: asyncio.AbstractEventLoop, inbox: asyncio.Queue[dict[str, Any] | None]) -> None:
    stdin = sys.stdin.buffer
    while True:
        line = stdin.readline(MAX_LINE + 1)
        if not line or len(line) > MAX_LINE:
            break
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if isinstance(message, dict):
            loop.call_soon_threadsafe(inbox.put_nowait, message)
    loop.call_soon_threadsafe(inbox.put_nowait, None)


async def _serve() -> None:
    global _loop
    _loop = asyncio.get_running_loop()
    inbox: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    threading.Thread(target=_reader, args=(_loop, inbox), daemon=True).start()
    tasks: set[asyncio.Task[None]] = set()
    while (message := await inbox.get()) is not None:
        if "method" in message:
            task = asyncio.create_task(_handle(message))
            tasks.add(task)
            task.add_done_callback(tasks.discard)
            continue
        future = _pending.get(message.get("id"))  # type: ignore[arg-type]
        if future is not None and not future.done():
            if "error" in message:
                error = message.get("error") or {}
                future.set_exception(RuntimeError(str(error.get("message", "error"))))
            else:
                future.set_result(message.get("result"))


def main() -> None:
    global _proto_out
    package, data_dir = Path(sys.argv[1]), Path(sys.argv[2])
    _proto_out = sys.stdout.buffer
    sys.stdout = _Log("info")
    sys.stderr = _Log("error")
    sys.modules["nyx"] = _make_module(data_dir)
    tools_dir = package / "tools"
    sys.path[:0] = [str(tools_dir), str(tools_dir / "lib")]
    try:
        importlib.import_module("main")
    except BaseException as e:  # se cuenta a Nyx y se sale
        print("".join(traceback.format_exception(e)), file=sys.stderr)
        _send({"method": "fatal", "params": {"text": f"{type(e).__name__}: {e}"[:500]}})
        sys.exit(3)
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
