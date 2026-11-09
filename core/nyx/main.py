"""Punto de entrada del núcleo de Nyx.

Lo lanza la app Tauri como proceso hijo. Contrato con el proceso principal:

- Token de sesión en la variable de entorno NYX_TOKEN (o --token en desarrollo).
- Al estar listo escribe en stdout una línea JSON: {"event": "ready", "port": N, "protocol": P}.
- Con --parent-pipe, termina cuando se cierra su stdin (el proceso principal ha salido).
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
import secrets
import sys
import threading

from nyx import __version__
from nyx.bridge.protocol import PROTOCOL_VERSION
from nyx.bridge.server import UIBridge
from nyx.bus import EventBus
from nyx.log import setup_logging
from nyx.paths import logs_dir

log = logging.getLogger("nyx")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="nyx", description="Núcleo de Nyx")
    p.add_argument("--port", type=int, default=0, help="puerto del WebSocket (0 = libre)")
    p.add_argument("--token", default=None, help="token de sesión (por defecto NYX_TOKEN)")
    p.add_argument("--print-token", action="store_true", help="muestra el token por stderr")
    p.add_argument("--parent-pipe", action="store_true", help="salir al cerrarse stdin")
    p.add_argument("--demo", action="store_true", help="recorre los estados sin voz")
    p.add_argument("--log-level", default="INFO")
    p.add_argument("--no-log-file", action="store_true")
    return p.parse_args(argv)


def _watch_parent(loop: asyncio.AbstractEventLoop, stop: asyncio.Event) -> None:
    """Hilo que espera el fin de stdin: el proceso principal ha terminado."""
    with contextlib.suppress(Exception):
        while sys.stdin.buffer.read(1024):
            pass
    loop.call_soon_threadsafe(stop.set)


async def run(args: argparse.Namespace) -> int:
    setup_logging(args.log_level, None if args.no_log_file else logs_dir())
    token = args.token or os.environ.get("NYX_TOKEN") or secrets.token_urlsafe(32)

    bus = EventBus()
    bridge = UIBridge(bus, token, port=args.port)
    port = await bridge.start()

    print(json.dumps({"event": "ready", "port": port, "protocol": PROTOCOL_VERSION}), flush=True)
    if args.print_token:
        print(f"token: {token}", file=sys.stderr, flush=True)
    log.info("Nyx %s listo (puerto %d)", __version__, port)

    stop = asyncio.Event()
    if args.parent_pipe:
        loop = asyncio.get_running_loop()
        threading.Thread(target=_watch_parent, args=(loop, stop), daemon=True).start()

    tasks: list[asyncio.Task[None]] = []
    if args.demo:
        from nyx.demo import run_demo

        tasks.append(asyncio.create_task(run_demo(bus), name="demo"))

    try:
        await stop.wait()
        log.info("Proceso principal cerrado: saliendo")
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await bridge.stop()
    return 0


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        sys.exit(asyncio.run(run(args)))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
