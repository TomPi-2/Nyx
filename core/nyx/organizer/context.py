"""Recordatorios por contexto (tarea 8.03): «cuando abra Discord, recuérdame…».

El detector de partida ya mira la ventana activa cada 2 s; cuando cambia de app avisa
(`ForegroundChanged`) y aquí se mira si hay un recordatorio para ella. Salta una vez, como una
alarma de Nyx (sonido, voz y notificación, con el mismo `AlarmRinger`), y queda como hecho.
Nunca en partida: si la app se abre jugando, espera a que acabe. Sin ubicación: «cuando llegue a
casa» no existe (sería seguir dónde estás).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from nyx.bus import EventBus
from nyx.game.detector import ForegroundChanged, GameStateChanged
from nyx.index.aliases import normalize
from nyx.organizer.store import AppReminder, OrganizerStore

if TYPE_CHECKING:
    from nyx.alarms.scheduler import AlarmScheduler

log = logging.getLogger(__name__)

#: Nyx no cuenta como «abrir una app».
_NYX = frozenset({"nyx-ui.exe", "nyx.exe"})


def matches(reminder: AppReminder, process: str, title: str) -> bool:
    """¿Es esta la app del recordatorio? Por su ejecutable si se sabía; si no, por el nombre."""
    if reminder.process:
        return process.lower() == reminder.process.lower()
    key = normalize(reminder.app)
    return bool(key) and (
        key in normalize(process.lower().removesuffix(".exe")) or key in normalize(title)
    )


class AppReminders:
    def __init__(
        self,
        bus: EventBus,
        store: OrganizerStore,
        alarms: AlarmScheduler,
        playing: Callable[[], bool],
    ) -> None:
        self.store = store
        self.alarms = alarms
        self.playing = playing
        self._waiting: dict[int, AppReminder] = {}
        bus.subscribe(ForegroundChanged, self._on_foreground)
        bus.subscribe(GameStateChanged, self._on_game)

    async def _on_foreground(self, event: ForegroundChanged) -> None:
        if event.process.lower() in _NYX:
            return
        for reminder in self.store.app_reminders():
            if not matches(reminder, event.process, event.title):
                continue
            if self.playing():
                self._waiting[reminder.id] = reminder  # al acabar la partida
            else:
                self._fire(reminder)

    async def _on_game(self, event: GameStateChanged) -> None:
        if event.active or not self._waiting:
            return
        pending = {r.id for r in self.store.app_reminders()}
        for reminder in self._waiting.values():
            if reminder.id in pending:  # no lo han borrado mientras tanto
                self._fire(reminder)
        self._waiting.clear()

    def _fire(self, reminder: AppReminder) -> None:
        log.info("Recordatorio al abrir %s", reminder.app)
        self.store.fire_app_reminder(reminder.id)
        self.alarms.add("alarm", self.alarms.clock() + 1, label=reminder.text)
