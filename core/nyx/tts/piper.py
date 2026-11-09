"""TTSService: Piper (ONNX) en la CPU. ~0,04 s por frase en el PC de referencia, así que la
voz no compite con el LLM ni con los juegos y apenas añade latencia."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from nyx.tts.base import TTSError

log = logging.getLogger(__name__)


class PiperTTS:
    def __init__(
        self,
        model: Path,
        config: Path,
        *,
        speaker: int | None = None,
        speed: float = 1.0,
    ) -> None:
        self._model = model
        self._config = config
        self.speaker = speaker
        self.speed = speed
        self.sample_rate = 22_050
        self._voice: Any = None
        # Una síntesis a la vez: el orden de las frases importa.
        self._lock = asyncio.Lock()

    def _synth(self, text: str) -> npt.NDArray[np.float32]:
        from piper import SynthesisConfig

        # length_scale > 1 = más despacio; speed > 1 = más deprisa.
        cfg = SynthesisConfig(speaker_id=self.speaker, length_scale=1.0 / self.speed)
        chunks = list(self._voice.synthesize(text, syn_config=cfg))
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate([c.audio_float_array for c in chunks]).astype(np.float32)

    def _load(self) -> Any:
        from piper import PiperVoice

        voice = PiperVoice.load(self._model, config_path=self._config)
        self._voice = voice
        self._synth("Hola.")  # calentamiento: la primera síntesis es más lenta
        return voice

    async def load(self) -> None:
        if not self._model.exists() or not self._config.exists():
            raise TTSError("faltan los archivos de la voz")
        try:
            data = json.loads(self._config.read_text(encoding="utf-8"))
            self.sample_rate = int(data["audio"]["sample_rate"])
        except (OSError, ValueError, KeyError) as e:
            raise TTSError(f"configuración de voz no válida: {e}") from e
        t0 = time.perf_counter()
        await asyncio.to_thread(self._load)
        log.info("Piper listo en %.1f s (%s)", time.perf_counter() - t0, self._model.stem)

    async def stream(self, text: str) -> AsyncIterator[npt.NDArray[np.float32]]:
        # Piper es tan rápido (~0,04 s por frase) que basta con un solo trozo.
        yield await self.synthesize(text)

    async def synthesize(self, text: str) -> npt.NDArray[np.float32]:
        if self._voice is None:
            raise TTSError("la voz no está cargada")
        async with self._lock:
            try:
                return await asyncio.to_thread(self._synth, text)
            except Exception as e:
                raise TTSError(str(e)) from e
