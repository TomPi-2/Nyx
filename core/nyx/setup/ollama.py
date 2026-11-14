r"""Ollama oficial, si falta (decisión del usuario, 2026-11-14; tareas 9.08 y 9.10).

En el primer arranque, el panel de descargas instala Ollama antes de bajar el cerebro. Se
instala con winget (viene con Windows 11 y comprueba la huella SHA-256 de lo que descarga, del
sitio oficial de Ollama), para el usuario y sin pedir permiso de administrador. Después se
abre (la app de la bandeja de Ollama, que arranca su servidor) y se espera a que conteste.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

PACKAGE = "Ollama.Ollama"
WINGET_TIMEOUT_S = 900
START_TIMEOUT_S = 60.0


def program_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama"


def installed() -> bool:
    return (program_dir() / "ollama.exe").exists() or shutil.which("ollama") is not None


async def install() -> bool:
    """Ollama con winget, para este usuario. True si ha quedado instalado."""
    winget = shutil.which("winget")
    if winget is None:
        log.warning("Sin winget: no puedo instalar Ollama")
        return False
    args = [
        winget, "install", "--id", PACKAGE, "--exact", "--silent", "--scope", "user",
        "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity",
    ]  # fmt: skip

    def run() -> int:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        result = subprocess.run(
            args, capture_output=True, timeout=WINGET_TIMEOUT_S, creationflags=flags, check=False
        )
        return result.returncode

    try:
        code = await asyncio.to_thread(run)
    except (OSError, subprocess.TimeoutExpired) as err:
        log.warning("No se pudo instalar Ollama: %s", err)
        return False
    log.info("winget install %s → %d", PACKAGE, code)
    return installed()


async def start(host: str) -> bool:
    """Abre Ollama (su app de la bandeja arranca el servidor) y espera a que conteste."""
    if await _answers(host):
        return True
    app = program_dir() / "ollama app.exe"
    exe = app if app.exists() else program_dir() / "ollama.exe"
    if not exe.exists():
        return False
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.Popen(  # noqa: ASYNC220 - se lanza y se deja correr (no se espera)
            [str(exe)] if exe == app else [str(exe), "serve"],
            creationflags=flags,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as err:
        log.warning("No se pudo abrir Ollama: %s", err)
        return False
    loop = asyncio.get_running_loop()
    deadline = loop.time() + START_TIMEOUT_S
    while loop.time() < deadline:
        if await _answers(host):
            return True
        await asyncio.sleep(1.0)
    return False


async def _answers(host: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=1.5) as http:
            return (await http.get(f"{host}/api/tags")).status_code == 200
    except httpx.HTTPError:
        return False
