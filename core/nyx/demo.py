"""Modo demostración: recorre los estados de Nyx para probar la interfaz sin voz."""

from __future__ import annotations

import asyncio
import math
import random

from nyx.bus import EventBus
from nyx.events import AudioLevel, BubbleHidden, BubbleShown, NyxState, StateChanged

LEVEL_HZ = 30


async def _levels(bus: EventBus, seconds: float, base: float) -> None:
    """Simula un nivel de audio con forma de habla a 30 Hz."""
    steps = int(seconds * LEVEL_HZ)
    for i in range(steps):
        t = i / LEVEL_HZ
        syllables = abs(math.sin(t * 7.0)) * abs(math.sin(t * 1.3 + 0.5))
        await bus.publish(AudioLevel(rms=min(1.0, base * syllables + random.uniform(0, 0.08))))
        await asyncio.sleep(1 / LEVEL_HZ)
    await bus.publish(AudioLevel(rms=0.0))


async def run_demo(bus: EventBus) -> None:
    async def state(s: NyxState) -> None:
        await bus.publish(StateChanged(s))

    while True:
        await state(NyxState.IDLE)
        await asyncio.sleep(2.0)

        # «Nyx, ¿cómo se dice hola en alemán?»
        await state(NyxState.LISTENING)
        await _levels(bus, 2.2, 0.9)
        await state(NyxState.THINKING)
        await asyncio.sleep(1.2)
        await state(NyxState.SPEAKING)
        await bus.publish(BubbleShown(display="Hallo", secondary="hola · alemán"))
        await _levels(bus, 2.0, 0.7)
        await asyncio.sleep(2.5)
        await bus.publish(BubbleHidden())

        await state(NyxState.IDLE)
        await asyncio.sleep(2.0)

        # «Nyx, abre Valorant»: acción silenciosa, sin burbuja.
        await state(NyxState.LISTENING)
        await _levels(bus, 1.5, 0.9)
        await state(NyxState.IDLE)
        await asyncio.sleep(2.0)

        # Petición que falla.
        await state(NyxState.LISTENING)
        await _levels(bus, 1.5, 0.9)
        await state(NyxState.THINKING)
        await asyncio.sleep(0.8)
        await state(NyxState.ERROR)
        await bus.publish(BubbleShown(display="No encuentro esa aplicación"))
        await asyncio.sleep(3.0)
        await bus.publish(BubbleHidden())
