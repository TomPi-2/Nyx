"""Rasgos de audio para el detector propio de «Nyx» (fase 4b).

Mismo camino que openWakeWord (código Apache-2.0; modelo base de Google, Apache-2.0):

    audio 16 kHz ─► espectrograma mel (ventana 512, salto 160 = 10 ms, 32 bandas)
              ─► modelo base: cada 76 ventanas mel → un vector de 96 (uno cada 80 ms)
              ─► el detector mira los últimos 16 vectores (~1,3 s)

`FeatureExtractor.clip` sirve para entrenar (clips enteros) y `StreamingFeatures` para Nyx
(bloques de 32 ms del micro). Dan lo mismo: lo comprueban las pruebas.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path

import numpy as np
import numpy.typing as npt

MEL_WINDOW = 512
MEL_HOP = 160
MEL_BANDS = 32
EMB_WINDOW = 76  # ventanas mel por vector
EMB_STEP = 8  # ventanas mel entre vectores (80 ms)
EMB_DIM = 96
N_EMB = 16  # vectores que mira el detector (~1,3 s)
CHUNK = EMB_STEP * MEL_HOP  # 1280 muestras: un vector nuevo
_OVERLAP = MEL_WINDOW - MEL_HOP  # 352: lo que hay que repetir para que las ventanas encajen

Floats = npt.NDArray[np.float32]


class FeatureExtractor:
    def __init__(self, melspec: Path, embedding: Path, threads: int = 1) -> None:
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        providers = ["CPUExecutionProvider"]
        self._mel = ort.InferenceSession(str(melspec), options, providers=providers)
        self._emb = ort.InferenceSession(str(embedding), options, providers=providers)

    def mels(self, audio: npt.NDArray[np.int16]) -> Floats:
        """(ventanas, 32). El audio va como int16 en float (así lo espera el modelo)."""
        if len(audio) < MEL_WINDOW:
            return np.zeros((0, MEL_BANDS), dtype=np.float32)
        x = audio.astype(np.float32)[None, :]
        out = self._mel.run(None, {"input": x})[0]
        spec: Floats = np.squeeze(out, axis=(0, 1)).astype(np.float32)
        return spec / 10.0 + 2.0  # la misma escala que usa openWakeWord

    def embed(self, windows: Floats) -> Floats:
        """(n, 76, 32) → (n, 96)."""
        if len(windows) == 0:
            return np.zeros((0, EMB_DIM), dtype=np.float32)
        out = self._emb.run(None, {"input_1": windows[..., None]})[0]
        return np.asarray(out.reshape(len(windows), EMB_DIM), dtype=np.float32)

    def clip(self, audio: npt.NDArray[np.int16]) -> Floats:
        """Todos los vectores de un clip, uno cada 80 ms: (n, 96)."""
        mels = self.mels(audio)
        starts = range(0, len(mels) - EMB_WINDOW + 1, EMB_STEP)
        if not len(starts):
            return np.zeros((0, EMB_DIM), dtype=np.float32)
        return self.embed(np.stack([mels[s : s + EMB_WINDOW] for s in starts]))


class StreamingFeatures:
    """Vectores al vuelo a partir de bloques del micro de cualquier tamaño."""

    def __init__(self, extractor: FeatureExtractor) -> None:
        self.extractor = extractor
        self.reset()

    def reset(self) -> None:
        # Audio aún sin convertir; empieza justo donde empieza la próxima ventana mel.
        self._buf = np.zeros(0, dtype=np.int16)
        self._mels: deque[Floats] = deque(maxlen=EMB_WINDOW)
        self._mel_count = 0  # ventanas mel desde el principio
        self.embeddings: deque[Floats] = deque(maxlen=N_EMB)

    def feed(self, frame: npt.NDArray[np.int16]) -> int:
        """Añade audio; devuelve cuántos vectores nuevos hay (0 o más)."""
        self._buf = np.concatenate([self._buf, frame])
        # Se calcula por tandas de ~80 ms (el modelo mel tiene un coste fijo por llamada).
        if len(self._buf) < CHUNK + _OVERLAP:
            return 0
        n = (len(self._buf) - MEL_WINDOW) // MEL_HOP + 1
        mels = self.extractor.mels(self._buf[: (n - 1) * MEL_HOP + MEL_WINDOW])
        self._buf = self._buf[n * MEL_HOP :]
        added = 0
        for row in mels[:n]:
            self._mels.append(row)
            self._mel_count += 1
            # Vector i = ventanas mel [8i, 8i + 76): igual que en `clip`.
            if self._mel_count >= EMB_WINDOW and (self._mel_count - EMB_WINDOW) % EMB_STEP == 0:
                window = np.stack(list(self._mels))[None, ...]
                self.embeddings.append(self.extractor.embed(window)[0])
                added += 1
        return added

    def window(self) -> Floats | None:
        """Los últimos 16 vectores (16, 96), o None si aún no hay bastante audio."""
        if len(self.embeddings) < N_EMB:
            return None
        return np.stack(list(self.embeddings))
