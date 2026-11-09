"""Interfaz común de los detectores de la palabra de activación (SPEC sección 2)."""

from __future__ import annotations

from typing import Protocol

from nyx.audio.capture import Frame


class WakeWordEngine(Protocol):
    def process(self, frame: Frame) -> bool:
        """Procesa un bloque de 32 ms. True si acaba de oírse la palabra."""
        ...

    def reset(self) -> None: ...
