"""Planificador de alarmas y temporizadores (SPEC secciones 7 y 14).

Una tarea asyncio duerme hasta la próxima alarma (o hasta que se añade o cancela una) y, al
llegar la hora, publica `AlarmFired` en el bus. Al arrancar, las que vencieron con el PC
apagado se avisan juntas con un solo `AlarmsMissed`: no suenan todas a la vez.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from nyx.alarms.store import Alarm, AlarmStore, Kind
from nyx.bus import EventBus

log = logging.getLogger(__name__)

# Una alarma que llega con menos retraso que esto suena igual (el PC estaba suspendido un
# momento, el bucle iba con retraso…); con más, se avisa como perdida.
LATE_GRACE_S = 120.0
MAX_SLEEP_S = 30.0  # se revisa al menos así de a menudo (suspensión, cambios de hora)


@dataclass(frozen=True, slots=True)
class AlarmFired:
    alarm: Alarm


@dataclass(frozen=True, slots=True)
class AlarmsMissed:
    """Alarmas que vencieron mientras Nyx no estaba en marcha."""

    alarms: tuple[Alarm, ...]


class AlarmScheduler:
    def __init__(
        self, store: AlarmStore, bus: EventBus, clock: Callable[[], float] = time.time
    ) -> None:
        self.store = store
        self.bus = bus
        self.clock = clock
        self._changed = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        now = self.clock()
        missed = [a for a in self.store.pending() if a.due < now - LATE_GRACE_S]
        for alarm in missed:
            self.store.mark_fired(alarm.id)
        if missed:
            log.info("Alarmas vencidas con Nyx cerrado: %d", len(missed))
            await self.bus.publish(AlarmsMissed(tuple(missed)))
        self._task = asyncio.create_task(self._run(), name="alarms")

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    def add(
        self, kind: Kind, due: float, *, label: str = "", duration_s: int | None = None
    ) -> Alarm:
        alarm = self.store.add(kind, due, label=label, duration_s=duration_s, now=self.clock())
        log.info(
            "%s para %s (%s)", kind, time.strftime("%d/%m %H:%M:%S", time.localtime(due)), alarm.id
        )
        self._changed.set()
        return alarm

    def cancel(self, alarm_id: str) -> bool:
        ok = self.store.cancel(alarm_id)
        self._changed.set()
        return ok

    def pending(self) -> list[Alarm]:
        return self.store.pending()

    async def fire_due(self) -> float | None:
        """Hace sonar las que ya tocan; devuelve cuándo toca la siguiente (o None)."""
        now = self.clock()
        upcoming: float | None = None
        for alarm in self.store.pending():
            if alarm.due <= now:
                if self.store.mark_fired(alarm.id):
                    await self.bus.publish(AlarmFired(alarm))
            else:
                upcoming = alarm.due
                break
        return upcoming

    async def _run(self) -> None:
        while True:
            try:
                upcoming = await self.fire_due()
            except Exception:
                log.exception("Error revisando alarmas")
                upcoming = None
            wait = MAX_SLEEP_S if upcoming is None else min(MAX_SLEEP_S, upcoming - self.clock())
            self._changed.clear()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._changed.wait(), max(0.05, wait))
