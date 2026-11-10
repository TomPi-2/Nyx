"""Detector propio de «Nyx» (fase 4): rasgos de features.py + nyx.onnx entrenado en
training/train.py. Misma interfaz que el de Vosk (WakeWordEngine).

Cada 80 ms el modelo da una probabilidad; salta cuando supera el umbral y no vuelve a saltar
hasta pasado `refractory_s` (una misma palabra da varias ventanas altas seguidas).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from nyx.audio.capture import FRAME_S, Frame
from nyx.wake.features import FeatureExtractor, StreamingFeatures

# El detector entrenado en training/ (versión 1, 2026-11-10; ver docs/benchmarks).
OWN_MODEL = Path(__file__).resolve().parent / "data" / "nyx-v1.onnx"
DEFAULT_THRESHOLD = 0.5
REFRACTORY_S = 1.0


def threshold_for(sensitivity: int) -> float:
    """Sensibilidad 1–10 de los ajustes (SPEC sección 4.7) → umbral: 10 salta con poco."""
    level = min(10, max(1, sensitivity))
    return round(0.9 - (level - 1) * 0.08, 2)  # 1 → 0,90 · 6 → 0,50 · 10 → 0,18


class OwnWakeWord:
    def __init__(
        self,
        model: Path,
        melspec: Path,
        embedding: Path,
        *,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> None:
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        self._session = ort.InferenceSession(
            str(model), options, providers=["CPUExecutionProvider"]
        )
        self.features = StreamingFeatures(FeatureExtractor(melspec, embedding))
        self.threshold = threshold
        self.last_score = 0.0
        self._cooldown = 0.0

    def process(self, frame: Frame) -> bool:
        self._cooldown = max(0.0, self._cooldown - FRAME_S)
        if not self.features.feed(frame):
            return False
        window = self.features.window()
        if window is None:
            return False
        out = self._session.run(None, {"x": window[None, ...].astype(np.float32)})[0]
        self.last_score = float(np.asarray(out).reshape(-1)[0])
        if self.last_score >= self.threshold and self._cooldown == 0.0:
            self._cooldown = REFRACTORY_S
            return True
        return False

    def reset(self) -> None:
        """Tras una activación: se conserva el audio reciente (si no, el detector quedaría
        ciego ~2 s mientras se llena otra vez la ventana)."""
        self.last_score = 0.0
        self._cooldown = REFRACTORY_S

    def clear(self) -> None:
        """Olvida también el audio (otro micrófono, otra grabación)."""
        self.features.reset()
        self.last_score = 0.0
        self._cooldown = 0.0
