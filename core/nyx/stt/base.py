"""Interfaz común de los motores de voz a texto (SPEC sección 2)."""

from __future__ import annotations

from typing import Protocol

import numpy as np
import numpy.typing as npt


class STTError(Exception):
    pass


# Por debajo de esto, Whisper no está seguro de lo que ha oído (paso 2 de Cerebro 2,
# 2026-11-24). Umbrales prudentes: se afinan con la batería de audio (C0).
NO_SPEECH_MAX = 0.6  # probabilidad de que no haya voz
LOGPROB_MIN = -1.0  # media del logaritmo de la probabilidad de cada palabra


class Transcript(str):
    """Lo transcrito, con la confianza de Whisper (`verbose_json` de whisper-server).

    Es un `str`: quien no mira la confianza lo usa como siempre. Un texto normal (de otro
    motor o de las pruebas) no es un Transcript y cuenta como seguro."""

    no_speech: float
    logprob: float

    def __new__(cls, text: str, no_speech: float = 0.0, logprob: float = 0.0) -> Transcript:
        made = super().__new__(cls, text)
        made.no_speech = no_speech
        made.logprob = logprob
        return made

    @property
    def unsure(self) -> bool:
        return self.no_speech > NO_SPEECH_MAX or self.logprob < LOGPROB_MIN


def unsure(text: str) -> bool:
    return isinstance(text, Transcript) and text.unsure


class STTEngine(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def transcribe(self, pcm: npt.NDArray[np.int16], prompt: str = "") -> str:
        """Audio de 16 kHz mono → texto."""
        ...
