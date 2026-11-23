"""Memoria corta: últimos turnos para entender «¿y en francés?» o «ciérralo» (SPEC sección 6)."""

from __future__ import annotations

import json
import time
from collections import deque
from collections.abc import Callable

from nyx.brain.base import ChatMessage

MAX_TURNS = 6
# Pasado este tiempo sin hablar, la conversación anterior ya no sirve de contexto.
EXPIRE_S = 3 * 60


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
        # Lo último que hizo Nyx (brain/agent.py, memory_note): va como contexto del mensaje,
        # no como un turno (el modelo imitaría el turno en vez de usarlo).
        self._action = ""

    def _expire(self) -> None:
        if self._clock() - self._last > self._expire_s:
            self._turns.clear()
            self._action = ""

    def set_action(self, note: str) -> None:
        if note:
            self._expire()
            self._action = note
            self._last = self._clock()

    def action(self) -> str:
        self._expire()
        return self._action

    def add(self, user: str, assistant: str, *, replace: bool = False) -> None:
        """`replace`: sustituye el último turno si es de la misma petición (bucle de agente)."""
        self._expire()
        if replace and self._turns and self._turns[-1][0] == user:
            self._turns.pop()
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
        except ValueError, AttributeError:
            spoken = assistant
        return user, spoken

    def clear(self) -> None:
        """Olvida la conversación y lo último hecho (las baterías empiezan así cada frase)."""
        self._turns.clear()
        self._action = ""
