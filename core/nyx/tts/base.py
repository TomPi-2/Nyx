"""Interfaz común de los motores de texto a voz (SPEC sección 2)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

import numpy as np
import numpy.typing as npt


class TTSError(Exception):
    pass


class TTSEngine(Protocol):
    sample_rate: int

    async def load(self) -> None: ...

    async def synthesize(self, text: str) -> npt.NDArray[np.float32]:
        """Texto → audio mono float32 a `sample_rate`."""
        ...

    def stream(self, text: str) -> AsyncIterator[npt.NDArray[np.float32]]:
        """El mismo audio a trozos, según se genera (la voz empieza antes)."""
        ...
