"""Traer al frente lo que Nyx acaba de abrir.

Windows no deja que un proceso en segundo plano (Nyx) ponga sus ventanas delante, así que
lo que se abría se quedaba detrás. Tras lanzar algo, se espera a que aparezca su ventana
(una nueva, o la que ya existía si la app es de instancia única) y se activa.
Se hace en segundo plano para no retrasar la respuesta.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Coroutine
from functools import lru_cache
from pathlib import Path
from typing import Any

from nyx.winapi import windows

log = logging.getLogger(__name__)

POLL_S = 0.15
TIMEOUT_S = 10.0
# Si no aparece una ventana nueva en este tiempo, se activa la que ya había.
REUSE_AFTER_S = 2.0

_pending: set[asyncio.Task[Any]] = set()


def snapshot() -> set[int]:
    """Ventanas abiertas antes de lanzar algo (para reconocer la nueva)."""
    try:
        return {w.hwnd for w in windows.list_windows()}
    except Exception:
        return set()


@lru_cache(maxsize=1)
def default_browser_process() -> str | None:
    """Ejecutable del navegador predeterminado (según la asociación de https)."""
    import winreg

    try:
        key = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            prog_id = str(winreg.QueryValueEx(k, "ProgId")[0])
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"{prog_id}\shell\open\command") as k:
            command = str(winreg.QueryValueEx(k, "")[0])
    except OSError:
        return None
    exe = command.split('"')[1] if command.startswith('"') else command.split(" ")[0]
    return Path(exe).name.lower() or None


async def bring_to_front(
    name: str,
    process: str | None,
    before: set[int],
    *,
    timeout_s: float = TIMEOUT_S,
    reuse_after_s: float = REUSE_AFTER_S,
) -> bool:
    t0 = time.monotonic()
    while (elapsed := time.monotonic() - t0) < timeout_s:
        found = await asyncio.to_thread(windows.find_windows, name, process)
        new = [w for w in found if w.hwnd not in before]
        target = new[0] if new else (found[0] if found and elapsed >= reuse_after_s else None)
        if target is not None:
            ok = await asyncio.to_thread(windows.activate, target.hwnd)
            log.info("Foco en «%s»: %s", target.title, "sí" if ok else "Windows no lo deja")
            return ok
        await asyncio.sleep(POLL_S)
    log.info("No ha aparecido ninguna ventana de %s para darle el foco", name)
    return False


def schedule(coro: Coroutine[Any, Any, Any]) -> None:
    """Lanza la tarea sin esperarla y guarda la referencia hasta que termine."""
    task = asyncio.create_task(coro, name="focus")
    _pending.add(task)
    task.add_done_callback(_pending.discard)


def request(
    name: str, process: str | None, before: set[int], reuse_after_s: float = REUSE_AFTER_S
) -> None:
    """Pide traer al frente la ventana de `name` en cuanto aparezca."""
    schedule(bring_to_front(name, process, before, reuse_after_s=reuse_after_s))
