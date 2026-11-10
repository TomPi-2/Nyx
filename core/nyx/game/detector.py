"""¿Hay una partida en marcha? (SPEC sección 9).

Se combinan tres señales cada 2 s:
1. Windows: `SHQueryUserNotificationState` dice si hay algo Direct3D a pantalla completa.
2. La ventana activa es de un juego: carpeta de juegos de las tiendas, juego de la caché o
   ejecutable conocido (winapi/games.py).
3. La lista del usuario: «tratar como juego» (siempre) y «no tratar como juego» (nunca).

Una pantalla completa Direct3D cuenta como juego salvo que sea un navegador o un reproductor
(un vídeo a pantalla completa no es una partida). La partida empieza en cuanto se detecta y
termina tras 5 s seguidos sin juego (histéresis: Alt+Tab no la corta).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from nyx.bus import EventBus
from nyx.winapi import games, windows

log = logging.getLogger(__name__)

POLL_S = 2.0
EXIT_AFTER_S = 5.0
# SHQueryUserNotificationState
QUNS_BUSY = 2  # una app a pantalla completa
QUNS_RUNNING_D3D_FULL_SCREEN = 3
QUNS_APP = 7  # app de la Store a pantalla completa
# Pantalla completa que no es una partida.
NOT_GAMES = frozenset(
    {
        "chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "opera_gx.exe", "brave.exe",
        "vivaldi.exe", "vlc.exe", "mpc-hc64.exe", "potplayermini64.exe", "explorer.exe",
        "powerpnt.exe", "nyx-ui.exe", "applicationframehost.exe",
    }
)  # fmt: skip
KNOWN_GAMES = frozenset(
    {
        "valorant-win64-shipping.exe", "league of legends.exe", "cs2.exe", "fortnite.exe",
        "fortniteclient-win64-shipping.exe", "r5apex.exe", "overwatch.exe", "gta5.exe",
        "rocketleague.exe", "eldenring.exe", "minecraft.exe", "javaw.exe",
    }
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class GameStateChanged:
    active: bool
    process: str = ""
    title: str = ""
    mode: str = "voice"  # «Nyx en partida»: off | voice | normal


@dataclass(frozen=True, slots=True)
class Probe:
    """Una lectura: ventana activa y estado de Windows."""

    process: str
    title: str
    hwnd: int
    fullscreen_d3d: bool


def notification_state() -> int:
    import ctypes

    state = ctypes.c_int(0)
    if ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state)) != 0:
        return 0
    return int(state.value)


def probe() -> Probe | None:
    fg = windows.foreground()
    if fg is None:
        return None
    state = notification_state()
    return Probe(fg.process, fg.title, fg.hwnd, state in (QUNS_RUNNING_D3D_FULL_SCREEN, QUNS_APP))


def looks_like_game(
    p: Probe,
    *,
    always: frozenset[str],
    never: frozenset[str],
    game_processes: frozenset[str],
    is_game_window: Callable[[int, str, set[str]], bool] = games.window_is_game,
) -> bool:
    process = p.process.lower()
    if process in never:
        return False
    if process in always or process in KNOWN_GAMES:
        return True
    if is_game_window(p.hwnd, process, set(game_processes)):
        return True
    return p.fullscreen_d3d and process not in NOT_GAMES


class GameDetector:
    def __init__(
        self,
        bus: EventBus,
        *,
        always: list[str] | None = None,
        never: list[str] | None = None,
        game_processes: Callable[[], set[str]] = set,
        read: Callable[[], Probe | None] = probe,
        clock: Callable[[], float] = time.monotonic,
        is_game_window: Callable[[int, str, set[str]], bool] = games.window_is_game,
        mode: Callable[[], str] = lambda: "voice",
    ) -> None:
        self.bus = bus
        self.mode = mode
        self.always = frozenset(a.lower() for a in always or [])
        self.never = frozenset(n.lower() for n in never or [])
        self.game_processes = game_processes
        self.read = read
        self.clock = clock
        self.is_game_window = is_game_window
        self.active = False
        self.process = ""
        self._last_seen = 0.0
        self._task: asyncio.Task[None] | None = None

    async def check(self) -> bool:
        """Una lectura; publica GameStateChanged si cambia. Devuelve si hay partida."""
        try:
            p = await asyncio.to_thread(self.read)
        except Exception:
            log.debug("No se pudo leer la ventana activa", exc_info=True)
            p = None
        now = self.clock()
        game = p is not None and await asyncio.to_thread(
            looks_like_game,
            p,
            always=self.always,
            never=self.never,
            game_processes=frozenset(self.game_processes()),
            is_game_window=self.is_game_window,
        )
        if game and p is not None:
            self._last_seen = now
            if not self.active:
                self.active, self.process = True, p.process
                log.info("Partida: %s («%s»)", p.process, p.title)
                await self.bus.publish(GameStateChanged(True, p.process, p.title, self.mode()))
        elif self.active and now - self._last_seen >= EXIT_AFTER_S:
            log.info("Fin de la partida (%s)", self.process)
            self.active = False
            await self.bus.publish(GameStateChanged(False, self.process, mode=self.mode()))
        return self.active

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="game-detector")

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _run(self) -> None:
        while True:
            await self.check()
            await asyncio.sleep(POLL_S)
