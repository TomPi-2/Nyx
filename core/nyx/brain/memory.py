"""Memoria corta: últimos turnos para entender «¿y en francés?» o «ciérralo» (SPEC sección 6)."""

from __future__ import annotations

import json
import time
from collections import deque
from collections.abc import Callable

from nyx.brain.base import ChatMessage

MAX_TURNS = 6
# Pasado este tiempo sin hablar, la conversación anterior ya no sirve de contexto.
EXPIRE_S = 10 * 60


class ShortMemory:
    def __init__(
        self,
        max_turns: int = MAX_TURNS,
        expire_s: float = EXPIRE_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._turns: deque[tuple[str, str]] = deque(maxlen=max_turns)
        self._expire_s = expire_s
        self._clock = clock
        self._last = clock()

    def _expire(self) -> None:
        if self._clock() - self._last > self._expire_s:
            self._turns.clear()

    def add(self, user: str, assistant: str) -> None:
        self._expire()
        self._turns.append((user, assistant))
        self._last = self._clock()

    def messages(self) -> list[ChatMessage]:
        self._expire()
        out: list[ChatMessage] = []
        for user, assistant in self._turns:
            out += [ChatMessage("user", user), ChatMessage("assistant", assistant)]
        return out

    def last_turn(self) -> tuple[str, str] | None:
        """(petición, lo que Nyx dijo) del último turno, si no ha caducado."""
        self._expire()
        if not self._turns:
            return None
        user, assistant = self._turns[-1]
        try:
            spoken = str(json.loads(assistant).get("spoken", assistant))
        except (ValueError, AttributeError):
            spoken = assistant
        return user, spoken

    def clear(self) -> None:
        self._turns.clear()
