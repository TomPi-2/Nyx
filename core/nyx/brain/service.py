"""Brain: arma el prompt, llama al LLM y traduce su salida en eventos para la voz y la burbuja.

Fase 2: solo respuestas informativas. El router rápido y las herramientas llegan en la fase 3.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime

from nyx.brain.base import ChatMessage, LLMEngine
from nyx.brain.memory import ShortMemory
from nyx.brain.prompts import context_message, system_message
from nyx.brain.reply import REPLY_SCHEMA, Reply, ReplyEvent, ReplyStreamParser

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ReplyDone:
    reply: Reply


class Brain:
    def __init__(
        self,
        llm: LLMEngine,
        memory: ShortMemory | None = None,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.llm = llm
        self.memory = memory or ShortMemory()
        self._clock = clock

    async def warmup(self) -> None:
        await self.llm.warmup([system_message()])

    def build_messages(self, text: str) -> list[ChatMessage]:
        return [
            system_message(),
            *self.memory.messages(),
            context_message(self._clock()),
            ChatMessage("user", text),
        ]

    async def respond(self, text: str) -> AsyncIterator[ReplyEvent | ReplyDone]:
        parser = ReplyStreamParser()
        async for chunk in self.llm.stream(self.build_messages(text), schema=REPLY_SCHEMA):
            for event in parser.feed(chunk):
                yield event
        reply = parser.finish()
        if not reply.spoken and not reply.display:
            log.warning("Respuesta vacía o no válida del LLM: %r", "".join(parser.raw)[:300])
        self.memory.add(text, reply.model_dump_json())
        yield ReplyDone(reply)
