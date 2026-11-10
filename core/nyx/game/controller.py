"""Lo que cambia al empezar y al terminar una partida (SPEC sección 9).

- Al empezar: la política de herramientas se activa, Nyx (y whisper) pasan a prioridad baja
  y, si se pidió, el LLM sale de la VRAM tras X minutos.
- Al terminar: todo vuelve a la normalidad, el LLM se recarga y se hace lo que se dejó
  pendiente, con un aviso breve.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from nyx.bus import EventBus
from nyx.events import BubbleHidden, BubbleShown
from nyx.game.detector import GameStateChanged
from nyx.game.policy import GameGate

if TYPE_CHECKING:
    from nyx.executor import Executor

log = logging.getLogger(__name__)

DONE_BUBBLE_S = 6.0


def set_low_priority(low: bool) -> None:
    """Prioridad «por debajo de lo normal» para Nyx y sus hijos (whisper-server)."""
    import psutil

    level = psutil.BELOW_NORMAL_PRIORITY_CLASS if low else psutil.NORMAL_PRIORITY_CLASS
    me = psutil.Process()
    for proc in [me, *me.children(recursive=True)]:
        with contextlib.suppress(psutil.Error):
            proc.nice(level)


class GameController:
    def __init__(
        self,
        bus: EventBus,
        gate: GameGate,
        executor: Executor | None,
        *,
        unload_llm: Callable[[], Awaitable[None]] | None = None,
        reload_llm: Callable[[], Awaitable[None]] | None = None,
        set_priority: Callable[[bool], None] = set_low_priority,
    ) -> None:
        self.bus = bus
        self.gate = gate
        self.executor = executor
        self.unload_llm = unload_llm
        self.reload_llm = reload_llm
        self.set_priority = set_priority
        self._unload_timer: asyncio.Task[None] | None = None
        self._unloaded = False
        self._hide: asyncio.Task[None] | None = None
        self._unsubscribe = bus.subscribe(GameStateChanged, self._on_change)

    async def close(self) -> None:
        self._unsubscribe()
        for task in (self._unload_timer, self._hide):
            if task is not None:
                task.cancel()

    async def _on_change(self, event: GameStateChanged) -> None:
        settings = self.gate.settings
        if event.active:
            self.gate.active = True
            if settings.low_priority:
                await asyncio.to_thread(self.set_priority, True)
            if settings.unload_llm_after_min and self.unload_llm is not None:
                self._unload_timer = asyncio.create_task(
                    self._unload_later(settings.unload_llm_after_min * 60), name="llm-unload"
                )
            return
        self.gate.active = False
        if self._unload_timer is not None:
            self._unload_timer.cancel()
            self._unload_timer = None
        if settings.low_priority:
            await asyncio.to_thread(self.set_priority, False)
        if self._unloaded and self.reload_llm is not None:
            self._unloaded = False
            with contextlib.suppress(Exception):
                await self.reload_llm()
        await self._run_deferred()

    async def _unload_later(self, seconds: float) -> None:
        await asyncio.sleep(seconds)
        if self.unload_llm is not None and self.gate.active:
            log.info("En partida desde hace un rato: el LLM sale de la VRAM")
            with contextlib.suppress(Exception):
                await self.unload_llm()
                self._unloaded = True

    async def _run_deferred(self) -> None:
        pending = self.gate.take()
        if not pending or self.executor is None:
            return
        done: list[str] = []
        failed: list[str] = []
        for item in pending:
            result = await self.executor.run(item.call, phrase=item.phrase)
            (done if result.ok else failed).append(item.summary)
        log.info("Al terminar la partida: hecho %s; falló %s", done, failed)
        secondary = ", ".join(done) + (f" · no pude: {', '.join(failed)}" if failed else "")
        await self.bus.publish(BubbleShown(display="Al terminar la partida", secondary=secondary))

        async def hide_later() -> None:
            await asyncio.sleep(DONE_BUBBLE_S)
            await self.bus.publish(BubbleHidden())

        self._hide = asyncio.create_task(hide_later(), name="game-deferred-bubble")
