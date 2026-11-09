"""Lo que pasa cuando suena una alarma (SPEC sección 11: aviso propio con sonido y además
notificación de Windows).

- Burbuja con el dato («10:50», «Tiempo», el texto del recordatorio) y el botón «Parar»;
  `alert=True` hace que la interfaz lance también la notificación de Windows.
- Un timbre cada pocos segundos durante como mucho un minuto y, tras el primero, la frase
  («Son las 10:50.»).
- Se calla con «Parar», al hablarle a Nyx (pasa a escuchar o a pensar) o al minuto. Un «para»
  justo después se entiende dirigido a la alarma y no a la música (`swallow`).
- Las alarmas que vencieron con Nyx cerrado se avisan una vez, con un solo timbre.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from collections.abc import Callable

import numpy as np

from nyx.alarms.scheduler import AlarmFired, AlarmsMissed
from nyx.alarms.spoken import fired_text, missed_text
from nyx.audio.playback import Player, Samples
from nyx.bus import EventBus
from nyx.events import (
    ActionChosen,
    BubbleAction,
    BubbleHidden,
    BubbleShown,
    NyxState,
    StateChanged,
)
from nyx.index.aliases import normalize
from nyx.tts.base import TTSEngine, TTSError

log = logging.getLogger(__name__)

RING_S = 60.0  # como mucho suena esto
CHIME_EVERY_S = 2.5
MISSED_BUBBLE_S = 30.0
STOP_WINDOW_S = 15.0  # «para» tras callar la alarma se refiere a ella
STOP_WORDS = {
    "para",
    "parala",
    "para la alarma",
    "para el temporizador",
    "apaga",
    "apagala",
    "apaga la alarma",
    "apaga el temporizador",
    "calla",
    "callate",
    "vale",
    "ya",
    "ya voy",
    "gracias",
    "ok",
    "stop",
}


def chime(sample_rate: int) -> Samples:
    """Dos notas de campana suaves (generadas: sin archivos de sonido con licencia)."""
    length = int(sample_rate * 1.0)
    t = np.arange(length, dtype=np.float32) / sample_rate
    out = np.zeros(length, dtype=np.float32)
    for start, freq in ((0.0, 880.0), (0.22, 1318.5)):
        mask = t >= start
        tt = t[mask] - start
        env = np.exp(-tt * 4.5)
        note = np.sin(2 * np.pi * freq * tt) + 0.35 * np.sin(2 * np.pi * 2 * freq * tt)
        out[mask] += (0.22 * env * note).astype(np.float32)
    fade = min(len(out), int(sample_rate * 0.01))
    out[:fade] *= np.linspace(0.0, 1.0, fade, dtype=np.float32)
    return out


class AlarmRinger:
    def __init__(
        self,
        bus: EventBus,
        *,
        tts: TTSEngine | None = None,
        player: Player | None = None,
        clock: Callable[[], float] = time.monotonic,
        ring_s: float = RING_S,
        chime_every_s: float = CHIME_EVERY_S,
    ) -> None:
        self.bus = bus
        self.tts = tts
        self.player = player
        self.clock = clock
        self.ring_s = ring_s
        self.chime_every_s = chime_every_s
        self._ring: asyncio.Task[None] | None = None
        self._button = ""
        self._stopped_at: float | None = None
        self._side: set[asyncio.Task[None]] = set()
        self._unsubscribe = [
            bus.subscribe(AlarmFired, self._on_fired),
            bus.subscribe(AlarmsMissed, self._on_missed),
            bus.subscribe(ActionChosen, self._on_action),
            bus.subscribe(StateChanged, self._on_state),
        ]

    @property
    def ringing(self) -> bool:
        return self._ring is not None and not self._ring.done()

    async def close(self) -> None:
        for unsubscribe in self._unsubscribe:
            unsubscribe()
        for task in list(self._side):
            task.cancel()
        await self._silence()

    def swallow(self, text: str) -> bool:
        """¿Es `text` un «para / vale / apágala» para la alarma que sonaba hace nada?"""
        if normalize(text) not in STOP_WORDS:
            return False
        if self.ringing:
            return True
        return self._stopped_at is not None and self.clock() - self._stopped_at < STOP_WINDOW_S

    async def stop(self) -> None:
        """Calla la alarma y quita su burbuja."""
        if not self.ringing:
            return
        await self._silence()
        await self.bus.publish(BubbleHidden())

    async def _silence(self) -> None:
        if self._ring is None:
            return
        task, self._ring = self._ring, None
        self._button = ""
        self._stopped_at = self.clock()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        if self.player is not None:
            self.player.clear()

    async def _on_fired(self, event: AlarmFired) -> None:
        await self._silence()  # si sonaba otra, la nueva la sustituye
        display, secondary, spoken = fired_text(event.alarm)
        log.info("Suena %s %s: %s", event.alarm.kind, event.alarm.id, spoken)
        self._button = f"alarm-stop-{uuid.uuid4().hex[:8]}"
        await self.bus.publish(
            BubbleShown(
                display=display,
                secondary=secondary,
                actions=(BubbleAction(self._button, "Parar", primary=True),),
                alert=True,
            )
        )
        self._ring = asyncio.create_task(self._ring_loop(spoken), name="alarm-ring")

    async def _ring_loop(self, spoken: str) -> None:
        try:
            end = self.clock() + self.ring_s
            first = True
            while self.clock() < end:
                await self._play_chime()
                if first and spoken:
                    first = False
                    await self._say(spoken)
                await asyncio.sleep(self.chime_every_s)
        finally:
            if self._ring is asyncio.current_task():  # se acabó el minuto sin pararla
                self._ring = None
                self._stopped_at = self.clock()
                await self.bus.publish(BubbleHidden())

    async def _play_chime(self) -> None:
        if self.player is not None:
            self.player.enqueue(chime(self.player.sample_rate))

    async def _say(self, text: str) -> None:
        if self.tts is None or self.player is None:
            return
        with contextlib.suppress(TTSError):
            await self.player.drain()
            self.player.enqueue(await self.tts.synthesize(text))

    async def _on_missed(self, event: AlarmsMissed) -> None:
        display, secondary = missed_text(event.alarms)
        await self.bus.publish(BubbleShown(display=display, secondary=secondary, alert=True))
        await self._play_chime()

        async def hide_later() -> None:
            await asyncio.sleep(MISSED_BUBBLE_S)
            if not self.ringing:
                await self.bus.publish(BubbleHidden())

        task = asyncio.create_task(hide_later(), name="alarm-missed-hide")
        self._side.add(task)
        task.add_done_callback(self._side.discard)

    async def _on_action(self, event: ActionChosen) -> None:
        if self._button and event.id == self._button:
            await self.stop()

    async def _on_state(self, event: StateChanged) -> None:
        # Hablarle a Nyx (o escribirle) calla la alarma; la burbuja la sustituye la respuesta.
        if event.state in (NyxState.LISTENING, NyxState.THINKING) and self.ringing:
            await self._silence()
