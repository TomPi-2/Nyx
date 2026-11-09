"""TTSService: Kokoro-82M en ONNX, en la CPU para no competir con el LLM ni con los juegos."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from nyx.tts.base import TTSError

log = logging.getLogger(__name__)
# phonemizer avisa de «words count mismatch» con números y siglas: es inofensivo.
logging.getLogger("phonemizer").setLevel(logging.ERROR)

SAMPLE_RATE = 24_000
# Hilos de la CPU para Kokoro: uno por núcleo físico, hasta 8. Medido en un Ryzen 7 7700X:
# 2 hilos 610 ms, 4 → 491 ms, 8 → 345 ms, 16 → 315 ms por una frase de 1,8 s.
# (El modelo int8 no es más rápido en esta CPU.)
THREADS = max(2, min(8, (os.cpu_count() or 4) // 2))


class KokoroTTS:
    sample_rate = SAMPLE_RATE

    def __init__(
        self,
        model: Path,
        voices: Path,
        *,
        voice: str = "ef_dora",
        speed: float = 1.0,
        lang: str = "es",
    ) -> None:
        self._model = model
        self._voices = voices
        self.voice = voice
        self.speed = speed
        self.lang = lang
        self._kokoro: Any = None
        # Kokoro no es seguro entre hilos: una síntesis a la vez.
        self._lock = asyncio.Lock()

    def _load(self) -> Any:
        import onnxruntime as ort
        from kokoro_onnx import Kokoro

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = THREADS
        opts.inter_op_num_threads = 1
        session = ort.InferenceSession(
            str(self._model), sess_options=opts, providers=["CPUExecutionProvider"]
        )
        kokoro = Kokoro.from_session(session, str(self._voices))
        voices = kokoro.get_voices()
        if self.voice not in voices:
            spanish = [v for v in voices if v.startswith(("ef_", "em_"))]
            fallback = spanish[0] if spanish else voices[0]
            log.warning("No existe la voz %s: uso %s", self.voice, fallback)
            self.voice = fallback
        # Primera síntesis de calentamiento: la primera de verdad sería mucho más lenta.
        kokoro.create("Hola.", voice=self.voice, speed=self.speed, lang=self.lang)
        return kokoro

    async def load(self) -> None:
        if not self._model.exists() or not self._voices.exists():
            raise TTSError("faltan los archivos de Kokoro")
        t0 = time.perf_counter()
        self._kokoro = await asyncio.to_thread(self._load)
        log.info("Kokoro listo en %.1f s (voz %s)", time.perf_counter() - t0, self.voice)

    async def synthesize(self, text: str) -> npt.NDArray[np.float32]:
        if self._kokoro is None:
            raise TTSError("Kokoro no está cargado")
        async with self._lock:
            try:
                samples, _sr = await asyncio.to_thread(
                    self._kokoro.create, text, voice=self.voice, speed=self.speed, lang=self.lang
                )
            except Exception as e:
                raise TTSError(str(e)) from e
        return np.asarray(samples, dtype=np.float32)
