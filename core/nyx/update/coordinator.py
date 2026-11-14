"""Cuándo se aplica una actualización ya descargada (SPEC §15, pasos 3 a 5; tarea 9.06).

La app (Velopack, `ui/src-tauri/src/updater.rs`) comprueba cada 6 h, descarga en segundo
plano y avisa (`UpdateOffered`). Aquí se decide cuándo aplicarla, según Ajustes → General:

- **Preguntar** (por defecto): en un buen momento, la isla pregunta «Nyx 1.4 está lista. Me
  reinicio unos 10 s. ¿Ahora?» con [Ahora] y [Más tarde]. «Más tarde» vuelve a preguntar en
  4 h; si antes se cierra Nyx o se apaga el PC, se aplica sola al volver a abrirla (Velopack).
- **Automático**: en un buen momento y con el PC sin usar 10 min, se aplica sola.
- **Solo avisar**: lo dice una vez, con un botón [Actualizar]; nunca se aplica sin pedirlo.

«Buen momento» es `UpdateGate` (9.05): sin petición en curso, sin partida, sin confirmaciones
ni nada pendiente. Antes de aplicarla se hace la copia de los datos (backup.py) y se le dice a
la app que cambie de versión (`UpdateApply`): para el núcleo y reinicia con la nueva.
"""

from __future__ import annotations

import asyncio
import contextlib
import ctypes
import logging
import time
from collections.abc import Callable
from ctypes import wintypes

from nyx.bus import EventBus
from nyx.events import (
    ActionChosen,
    BubbleAction,
    BubbleHidden,
    BubbleShown,
    UpdateApply,
    UpdateOffered,
)
from nyx.settings.model import Settings
from nyx.update.backup import make_backup
from nyx.update.moment import UpdateGate

log = logging.getLogger(__name__)

#: «Más tarde»: cuándo se vuelve a preguntar.
ASK_AGAIN_S = 4 * 3600
#: Automático: el PC tiene que llevar este rato sin teclado ni ratón.
IDLE_FOR_AUTO_S = 10 * 60
#: Cada cuánto se mira si ya es buen momento.
POLL_S = 30.0

NOW, LATER, UPDATE = "update-now", "update-later", "update-go"


def idle_seconds() -> float:
    """Segundos sin teclado ni ratón (GetLastInputInfo)."""

    class LastInput(ctypes.Structure):
        _fields_ = (("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD))

    info = LastInput()
    info.cbSize = ctypes.sizeof(info)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    now = int(ctypes.windll.kernel32.GetTickCount()) & 0xFFFFFFFF
    return float((now - int(info.dwTime)) & 0xFFFFFFFF) / 1000.0


class UpdateCoordinator:
    def __init__(
        self,
        bus: EventBus,
        settings: Settings,
        gate: UpdateGate,
        *,
        idle: Callable[[], float] = idle_seconds,
        clock: Callable[[], float] = time.monotonic,
        backup: Callable[[str], object] = make_backup,
        poll_s: float = POLL_S,
    ) -> None:
        self.bus = bus
        self.settings = settings
        self.gate = gate
        self._idle = idle
        self._clock = clock
        self._backup = backup
        self._poll_s = poll_s
        self.version: str | None = None
        self._ask_after = 0.0
        self._told = False  # «Solo avisar»: ya se ha dicho
        self._applying = False
        self._task: asyncio.Task[None] | None = None
        self._unsubscribe = [
            bus.subscribe(UpdateOffered, self._on_offered),
            bus.subscribe(ActionChosen, self._on_action),
        ]

    def close(self) -> None:
        for unsubscribe in self._unsubscribe:
            unsubscribe()
        if self._task is not None:
            self._task.cancel()

    async def _on_offered(self, event: UpdateOffered) -> None:
        if self.version == event.version:
            return
        log.info("Versión nueva descargada: %s", event.version)
        self.version = event.version
        self._ask_after = 0.0
        self._told = False
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._watch(), name="update-watch")

    async def _watch(self) -> None:
        while self.version is not None and not self._applying:
            await self.step()
            await asyncio.sleep(self._poll_s)

    async def step(self) -> None:
        """Una vuelta: si es momento, pregunta, avisa o la aplica (según el ajuste)."""
        version = self.version
        if version is None or self._applying:
            return
        mode = self.settings.updates.mode
        if mode == "avisar":
            if not self._told:
                self._told = True
                await self.bus.publish(
                    BubbleShown(
                        display=f"Nyx {version} está lista",
                        secondary="Se instala cuando quieras",
                        actions=(BubbleAction(UPDATE, "Actualizar", primary=True),),
                        kind="confirm",
                    )
                )
            return
        if not self.gate.ready():
            return
        if mode == "automatico":
            if self._idle() >= IDLE_FOR_AUTO_S:
                await self.apply()
            return
        if self._clock() >= self._ask_after:
            self._ask_after = self._clock() + ASK_AGAIN_S
            await self.bus.publish(
                BubbleShown(
                    display=f"Nyx {version} está lista",
                    secondary="Me reinicio unos 10 s. ¿Ahora?",
                    actions=(
                        BubbleAction(NOW, "Ahora", primary=True),
                        BubbleAction(LATER, "Más tarde"),
                    ),
                    kind="confirm",
                )
            )

    async def _on_action(self, event: ActionChosen) -> None:
        if event.id in (NOW, UPDATE):
            await self.apply()
        elif event.id == LATER:
            self._ask_after = self._clock() + ASK_AGAIN_S
            await self.bus.publish(BubbleHidden())

    async def apply(self) -> None:
        """Copia de los datos y a la app: que pare el núcleo y cambie de versión."""
        version = self.version
        if version is None or self._applying:
            return
        self._applying = True
        log.info("Aplicando la actualización a %s", version)
        with contextlib.suppress(Exception):  # sin copia también se puede (migrations la hace)
            await asyncio.to_thread(self._backup, version)
        await self.bus.publish(
            BubbleShown(display=f"Me actualizo a la {version}", secondary="Vuelvo enseguida")
        )
        await self.bus.publish(UpdateApply(version))
