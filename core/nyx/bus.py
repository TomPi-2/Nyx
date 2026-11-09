"""Bus de eventos asyncio: los servicios publican y se suscriben por tipo de evento."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

log = logging.getLogger(__name__)

E = TypeVar("E")
Handler = Callable[[Any], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: defaultdict[type, list[Handler]] = defaultdict(list)

    def subscribe(
        self, event_type: type[E], handler: Callable[[E], Awaitable[None]]
    ) -> Callable[[], None]:
        """Registra un manejador. Devuelve una función para cancelar la suscripción."""
        self._handlers[event_type].append(handler)

        def unsubscribe() -> None:
            if handler in self._handlers[event_type]:
                self._handlers[event_type].remove(handler)

        return unsubscribe

    async def publish(self, event: object) -> None:
        """Entrega el evento a los manejadores de su tipo y de sus clases base.

        Un manejador que falla no impide que los demás reciban el evento.
        """
        handlers = [h for cls in type(event).__mro__ for h in self._handlers.get(cls, ())]
        if not handlers:
            return
        results = await asyncio.gather(*(h(event) for h in handlers), return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                log.error("Fallo en un manejador de %s", type(event).__name__, exc_info=result)
