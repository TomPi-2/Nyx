"""Detección de voz (Silero VAD en ONNX) y corte de la frase al dejar de hablar."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import numpy.typing as npt

from nyx.audio.capture import FRAME_S, FRAME_SAMPLES, SAMPLE_RATE, Frame

CONTEXT_SAMPLES = 64  # Silero v5 a 16 kHz: 64 muestras del bloque anterior delante de cada bloque


class VoiceDetector(Protocol):
    def __call__(self, frame: Frame) -> float:
        """Probabilidad (0–1) de que el bloque contenga voz."""
        ...

    def reset(self) -> None: ...


class SileroVAD:
    def __init__(self, model: Path) -> None:
        import onnxruntime as ort

        opts = ort.SessionOptions()
        # Un hilo basta (≈0,2 ms por bloque) y no compite con el juego ni con el LLM.
        opts.intra_op_num_threads = 1
        opts.inter_op_num_threads = 1
        self._session: Any = ort.InferenceSession(
            str(model), sess_options=opts, providers=["CPUExecutionProvider"]
        )
        self._sr = np.array(SAMPLE_RATE, dtype=np.int64)
        self.reset()

    def reset(self) -> None:
        self._state: npt.NDArray[np.float32] = np.zeros((2, 1, 128), dtype=np.float32)
        self._context: npt.NDArray[np.float32] = np.zeros((1, CONTEXT_SAMPLES), dtype=np.float32)

    def __call__(self, frame: Frame) -> float:
        if frame.shape[0] != FRAME_SAMPLES:
            raise ValueError(f"Silero necesita bloques de {FRAME_SAMPLES} muestras")
        x = (frame.astype(np.float32) / 32768.0)[np.newaxis, :]
        x = np.concatenate([self._context, x], axis=1)
        out, self._state = self._session.run(
            None, {"input": x, "state": self._state, "sr": self._sr}
        )
        self._context = x[:, -CONTEXT_SAMPLES:]
        return float(out[0][0])


class EndReason(StrEnum):
    SILENCE = "silence"  # habló y se calló
    MAX_LENGTH = "max_length"  # 15 s
    NO_SPEECH = "no_speech"  # no llegó a hablar
    MANUAL = "manual"  # soltó el atajo de hablar


@dataclass
class Endpointer:
    """Decide cuándo termina la frase a partir de la probabilidad de voz de cada bloque.

    Histéresis: empieza a contar como voz por encima de `start_threshold` y como silencio
    por debajo de `end_threshold`, para no cortar en las pausas cortas.
    """

    silence_ms: int = 700
    max_s: float = 15.0
    start_timeout_s: float = 4.0
    start_threshold: float = 0.5
    end_threshold: float = 0.35
    speech_started: bool = field(default=False, init=False)
    _elapsed: float = field(default=0.0, init=False)
    _silence: float = field(default=0.0, init=False)

    def push(self, prob: float) -> EndReason | None:
        self._elapsed += FRAME_S
        if not self.speech_started:
            if prob >= self.start_threshold:
                self.speech_started = True
            elif self._elapsed >= self.start_timeout_s:
                return EndReason.NO_SPEECH
        else:
            self._silence = self._silence + FRAME_S if prob < self.end_threshold else 0.0
            if self._silence * 1000 >= self.silence_ms:
                return EndReason.SILENCE
        if self._elapsed >= self.max_s:
            return EndReason.MAX_LENGTH
        return None
