"""Interfaz común de los motores de voz a texto (SPEC sección 2)."""

from __future__ import annotations

from typing import Protocol

import numpy as np
import numpy.typing as npt


class STTError(Exception):
    pass


class STTEngine(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def transcribe(self, pcm: npt.NDArray[np.int16], prompt: str = "") -> str:
        """Audio de 16 kHz mono → texto."""
        ...
