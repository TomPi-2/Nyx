r"""Ollama oficial, si falta (decisión del usuario, 2026-11-14; tareas 9.08 y 9.10).

En el primer arranque, el panel de descargas instala Ollama antes de bajar el cerebro. Se
instala con winget (viene con Windows 11 y comprueba la huella SHA-256 de lo que descarga, del
sitio oficial de Ollama), para el usuario y sin pedir permiso de administrador. Después se
arranca solo su servidor, oculto, y se espera a que conteste.

Nyx no abre nunca la app de Ollama ni su ventana. Su instalador sí la abre al acabar y la pone
a arrancar con Windows: si Nyx acaba de instalarlo, la cierra y manda ese acceso directo de
inicio a la papelera (Nyx arranca el servidor cuando lo necesita).
"""

from __future__ import annotations

import asyncio
import contextlib
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
    if installed():
        await asyncio.to_thread(_quiet_after_install)
    return installed()


def _quiet_after_install() -> None:
    """Lo que abre el instalador de Ollama por su cuenta: su app (con ventana) y su arranque
    con Windows. Nyx no abre nada que el usuario no haya pedido."""
    import psutil

    for proc in psutil.process_iter(["name"]):
        if (proc.info.get("name") or "").lower() == "ollama app.exe":
            with contextlib.suppress(psutil.Error):
                proc.terminate()
    startup = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu"
    link = startup / "Programs" / "Startup" / "Ollama.lnk"
    if link.is_file():
        from send2trash import send2trash

        try:
            send2trash(str(link))  # a la papelera, nunca borrado del todo
        except OSError as err:
            log.info("No se pudo quitar el arranque de Ollama: %s", err)


async def start(host: str) -> bool:
    """Arranca el servidor de Ollama, oculto (nunca su app ni su ventana), y espera a que
    conteste."""
    from nyx.brain.ollama import launch_ollama

    if await _answers(host):
        return True
    if not await asyncio.to_thread(launch_ollama):
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
