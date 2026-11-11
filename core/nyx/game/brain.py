"""El cerebro durante la partida (0.5, bloque 4; docs/benchmarks/partida-*.md).

Nyx usa un solo modelo, el 7B, y en partida se queda donde está, en la tarjeta gráfica:
medido en Rocket League con la RX 7700 XT, cuesta un 3,4 % de FPS y no da tirones (en el
procesador, un 23 %). Decisión del 2026-11-11: sin el 14B no hace falta cambiar de modelo
al entrar y salir del juego (con Alt+Tab, ese cambio dejaba el 14B junto al juego unos
segundos y el juego iba a tirones).

Lo único que se puede elegir es «Solo órdenes» (`game.brain = "off"`): mientras se juega, el
modelo sale de la memoria, el router sigue (música, volumen, alarmas…) y las preguntas se
dejan para después.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Awaitable, Callable
from typing import Protocol

from nyx.game.policy import GameGate

log = logging.getLogger(__name__)


class UnloadableLLM(Protocol):
    async def unload(self) -> None: ...


class GameBrain:
    def __init__(
        self, gate: GameGate, llm: UnloadableLLM, warmup: Callable[[], Awaitable[None]]
    ) -> None:
        self.gate = gate
        self.llm = llm
        self.warmup = warmup

    async def start(self) -> None:
        """Al empezar la partida."""
        if self.gate.settings.brain != "off":
            return
        log.info("En partida, solo órdenes: el modelo sale de la memoria")
        self.gate.brain_off = True
        with contextlib.suppress(Exception):
            await self.llm.unload()

    async def stop(self) -> None:
        """Al terminar: si se apartó, vuelve ya cargado para la siguiente petición."""
        if not self.gate.brain_off:
            return
        self.gate.brain_off = False
        log.info("Fin de la partida: vuelve el cerebro")
        with contextlib.suppress(Exception):
            await self.warmup()
