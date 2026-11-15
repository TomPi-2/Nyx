r"""Everything (voidtools, licencia MIT): búsqueda de archivos instantánea, opcional.

Nyx lo usa con su línea de órdenes, es.exe (nyx/winapi/search.py), y Everything tiene que
estar abierto (en segundo plano) para que es.exe conteste. Desde el asistente se instala con
winget, que viene con Windows 11 y comprueba la integridad de lo que descarga; Everything se
instala para todo el equipo, así que Windows pide permiso.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

PACKAGES = ("voidtools.Everything", "voidtools.Everything.Cli")
WINGET_TIMEOUT_S = 600


def _program() -> Path | None:
    """Everything.exe, si está instalado."""
    bases = (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"))
    for base in bases:
        if base and (exe := Path(base) / "Everything" / "Everything.exe").exists():
            return exe
    return None


def _running() -> bool:
    try:
        import psutil

        return any(
            (p.info.get("name") or "").lower() == "everything.exe"
            for p in psutil.process_iter(["name"])
        )
    except Exception:
        return False


def status() -> dict[str, bool]:
    from nyx.winapi.search import everything_exe

    return {
        "installed": _program() is not None,
        "running": _running(),
        "cli": everything_exe() is not None,
    }


async def install() -> bool:
    """Everything y su línea de órdenes, con winget. True si los dos quedan instalados."""
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    ok = True
    for package in PACKAGES:
        try:
            proc = await asyncio.create_subprocess_exec(
                "winget",
                "install",
                "--id",
                package,
                "--exact",
                "--silent",
                "--accept-package-agreements",
                "--accept-source-agreements",
                "--disable-interactivity",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                creationflags=flags,
            )
            code = await asyncio.wait_for(proc.wait(), WINGET_TIMEOUT_S)
        except (OSError, TimeoutError) as err:
            log.warning("winget no pudo instalar %s: %s", package, err)
            ok = False
            continue
        # 0 = instalado; -1978335189 (0x8A15002B) = ya estaba instalado y al día.
        if code not in (0, -1978335189):
            log.warning("winget %s terminó con el código %s", package, code)
            ok = False
    if ok:
        start()
    return ok


def start() -> bool:
    """Abre Everything en segundo plano (en la bandeja). True si se ha podido."""
    exe = _program()
    if exe is None:
        return False
    if _running():
        return True
    try:
        # En su carpeta: si heredara la de Nyx, no dejaría reinstalarla (I-110).
        subprocess.Popen([str(exe), "-startup"], close_fds=True, cwd=exe.parent)
    except OSError as err:
        log.warning("No se pudo abrir Everything: %s", err)
        return False
    return True
