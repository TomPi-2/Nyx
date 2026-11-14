"""Punto de entrada del núcleo de Nyx.

Lo lanza la app Tauri como proceso hijo. Contrato con el proceso principal:

- Token de sesión en la variable de entorno NYX_TOKEN (o --token en desarrollo).
- Al estar listo escribe en stdout una línea JSON: {"event": "ready", "port": N, "protocol": P}.
- Con --parent-pipe, termina cuando muere el proceso principal: vigila el PID de
  NYX_PARENT_PID (o, si no lo hay, el cierre de stdin).

Sin --demo arranca el bucle de voz (fase 2). `nyx --ask "pregunta"` responde una vez y sale.
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
from typing import Any

from nyx import __version__
from nyx.bridge.protocol import PROTOCOL_VERSION, GlassInfo, ToolInfo, VoiceInfo
from nyx.bridge.server import UIBridge
from nyx.bus import EventBus
from nyx.events import TextEntered
from nyx.log import setup_logging
from nyx.models import MODELS, download_all
from nyx.paths import logs_dir
from nyx.services import Services, whisper_server_path
from nyx.services import build as build_services
from nyx.settings import load_settings
from nyx.settings.live import SettingsService
from nyx.setup.service import SetupService
from nyx.tts.voices import VOICES
from nyx.winjob import kill_children_on_exit

log = logging.getLogger("nyx")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="nyx", description="Núcleo de Nyx")
    p.add_argument("--port", type=int, default=0, help="puerto del WebSocket (0 = libre)")
    p.add_argument("--token", default=None, help="token de sesión (por defecto NYX_TOKEN)")
    p.add_argument("--print-token", action="store_true", help="muestra el token por stderr")
    p.add_argument("--parent-pipe", action="store_true", help="salir al cerrarse stdin")
    p.add_argument("--demo", action="store_true", help="recorre los estados sin voz")
    p.add_argument("--no-voice", action="store_true", help="sin micrófono: solo entrada por texto")
    p.add_argument("--ask", metavar="TEXTO", help="hace una pregunta, la responde y sale")
    p.add_argument(
        "--download-models", action="store_true", help="descarga los modelos que falten y sale"
    )
    p.add_argument("--log-level", default="INFO")
    p.add_argument("--no-log-file", action="store_true")
    return p.parse_args(argv)


def _quiet_connection_reset(loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
    """Silencia un aviso conocido de asyncio en Windows (ConnectionResetError al cerrar un
    socket que el otro lado ya cerró, bpo-39232); el resto va al manejador normal."""
    if isinstance(context.get("exception"), ConnectionResetError):
        log.debug("Conexión cerrada por el otro lado: %s", context.get("message"))
        return
    loop.default_exception_handler(context)


PARENT_POLL_S = 1.0


async def _watch_parent_pid(pid: int, stop: asyncio.Event) -> None:
    """Sale cuando muere el proceso principal (Tauri), aunque muera de golpe.

    No se lee stdin: en Windows, una lectura pendiente en una tubería bloquea cualquier otra
    consulta sobre ella, y PyTorch (Pocket TTS) hace una al cargar: el núcleo se colgaba.
    """
    import psutil

    try:
        parent = psutil.Process(pid)
        started = parent.create_time()
    except psutil.Error:
        stop.set()
        return
    while not stop.is_set():
        try:
            alive = parent.is_running() and parent.create_time() == started
        except psutil.Error:
            alive = False
        if not alive:
            log.info("El proceso principal (%d) ya no existe", pid)
            stop.set()
            return
        await asyncio.sleep(PARENT_POLL_S)


def _watch_stdin(loop: asyncio.AbstractEventLoop, stop: asyncio.Event) -> None:
    """Respaldo sin NYX_PARENT_PID: espera el fin de stdin (no usar con PyTorch, ver arriba)."""
    with contextlib.suppress(Exception):
        while sys.stdin.buffer.read(1024):
            pass
    loop.call_soon_threadsafe(stop.set)


async def run(args: argparse.Namespace) -> int:
    setup_logging(args.log_level, None if args.no_log_file else logs_dir())
    # Si el núcleo muere de golpe, whisper-server y demás hijos mueren con él.
    kill_children_on_exit()
    asyncio.get_running_loop().set_exception_handler(_quiet_connection_reset)
    token = args.token or os.environ.get("NYX_TOKEN") or secrets.token_urlsafe(32)
    settings = load_settings()
    if args.parent_pipe and not args.demo:
        # Lanzado por la app: nunca dos núcleos escuchando el micrófono a la vez.
        from nyx.single import take_over

        take_over()

    bus = EventBus()
    bridge = UIBridge(
        bus,
        token,
        port=args.port,
        indicator_size=settings.appearance.indicator_size,
        glass=GlassInfo.model_validate(settings.appearance.glass.model_dump()),
        tools=tool_infos(),
        voices=[VoiceInfo(id=v.id, label=v.label) for v in VOICES.values()],
        look={
            "font": settings.appearance.font,
            "nyx_color": settings.appearance.nyx_color,
            "panel_tint": settings.appearance.panel_tint,
            "ready_indicator": settings.appearance.ready_indicator,
        },
        onboarding_done=settings.onboarding.done or args.demo,
    )
    # Ajustes desde la ventana de Ajustes: se aplican sobre este mismo objeto (SPEC 13).
    settings_service = SettingsService(bus, settings, devices=audio_devices)
    port = await bridge.start()

    print(json.dumps({"event": "ready", "port": port, "protocol": PROTOCOL_VERSION}), flush=True)
    if args.print_token:
        print(f"token: {token}", file=sys.stderr, flush=True)
    log.info("Nyx %s listo (puerto %d)", __version__, port)

    stop = asyncio.Event()
    watcher: asyncio.Task[None] | None = None
    if args.parent_pipe:
        parent_pid = os.environ.get("NYX_PARENT_PID", "")
        if parent_pid.isdigit():
            watcher = asyncio.create_task(_watch_parent_pid(int(parent_pid), stop), name="parent")
        else:
            loop = asyncio.get_running_loop()
            threading.Thread(target=_watch_stdin, args=(loop, stop), daemon=True).start()

    tasks: list[asyncio.Task[None]] = []
    services: Services | None = None
    # Asistente y Ajustes → Cerebro, Caché, Ayuda y Privacidad. La caché y los atajos
    # aprendidos existen cuando los servicios están en marcha.
    setup = SetupService(
        bus,
        settings,
        index=lambda: services.index if services is not None else None,
        shortcuts=lambda: services.pipeline.shortcuts if services is not None else None,
        whisper_server=lambda: whisper_server_path(settings),
    )
    try:
        if args.demo:
            from nyx.demo import run_demo

            tasks.append(asyncio.create_task(run_demo(bus), name="demo"))
        else:
            voice = not (args.no_voice or args.ask)
            services = await build_services(bus, settings, voice=voice)
            tasks.append(asyncio.create_task(services.pipeline.run(), name="pipeline"))
            if args.ask:
                await bus.publish(TextEntered(args.ask))
                await services.pipeline.wait_idle()
                stop.set()
        await stop.wait()
        log.info("Saliendo")
    finally:
        if watcher is not None:
            watcher.cancel()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if services is not None:
            await services.close()
        settings_service.close()
        await setup.close()
        await bridge.stop()
    return 0


def audio_devices() -> tuple[list[str], list[str]]:
    """Micrófonos y altavoces para Ajustes → Voz."""
    from nyx.audio.devices import device_names

    return device_names("input"), device_names("output")


def tool_infos() -> list[ToolInfo]:
    """Herramientas para la lista de políticas en partida (Ajustes → Modo partida)."""
    from nyx.tools.registry import default_registry

    return [
        ToolInfo(name=t.name, risk=t.risk.value, game_policy=t.game_policy.value)
        for t in default_registry().all()
        if t.name != "wait_for_window"  # paso interno de los planes, no una acción
    ]


def download_models() -> int:
    settings = load_settings()
    # Si el modelo de whisper ya está configurado en otra carpeta, no se descarga otra vez.
    stt_elsewhere = settings.stt.model.exists() and settings.stt.model != MODELS["stt"].path()
    return download_all(skip=frozenset({"stt"}) if stt_elsewhere else frozenset())


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if args.download_models:
        sys.exit(download_models())
    try:
        sys.exit(asyncio.run(run(args)))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
