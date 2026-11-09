r"""TTSService: Pocket TTS (Kyutai, pesos CC BY 4.0) en la CPU, con la voz española «lola».

Genera a trozos: el primer trozo de audio sale en ~0,08 s aunque la frase tarde ~0,8 s
(medido en el PC de referencia), así que Nyx empieza a hablar casi al instante. Con 2 hilos
va igual de rápido que con 8, y molesta menos a los juegos.

Los modelos se guardan en %LOCALAPPDATA%\Nyx\models\hf (no en la caché del usuario).
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from nyx.paths import models_dir
from nyx.tts.base import TTSError
from nyx.tts.spoken import to_spoken

log = logging.getLogger(__name__)

THREADS = 2
SAMPLE_RATE = 24_000


def cache_dir() -> Path:
    return models_dir() / "hf"


def _configure_cache() -> None:
    """Antes de importar huggingface_hub: dónde guardar y sin telemetría."""
    os.environ.setdefault("HF_HUB_CACHE", str(cache_dir()))
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")


def _redirect_voice_cache() -> None:
    """Pocket TTS guarda las voces en ~/.cache/pocket_tts: se llevan a la carpeta de Nyx."""
    from pocket_tts.utils import utils

    def nyx_cache() -> Path:
        path = cache_dir() / "pocket_tts"
        path.mkdir(parents=True, exist_ok=True)
        return path

    if hasattr(utils, "make_cache_directory"):
        utils.make_cache_directory = nyx_cache


Samples = npt.NDArray[np.float32]


class PocketTTS:
    sample_rate = SAMPLE_RATE

    def __init__(self, voice: str = "lola", language: str = "spanish", speed: float = 1.0) -> None:
        self.voice = voice
        self.language = language
        self.speed = speed  # Pocket no cambia la velocidad: se ignora (ver Ajustes, fase 5)
        self._model: Any = None
        self._state: Any = None
        self._lock = asyncio.Lock()  # el modelo no es seguro entre hilos

    def _load(self) -> None:
        _configure_cache()
        import torch
        from pocket_tts import TTSModel

        _redirect_voice_cache()
        torch.set_num_threads(THREADS)
        self._model = TTSModel.load_model(language=self.language)
        self._state = self._model.get_state_for_audio_prompt(self.voice)
        self.sample_rate = int(self._model.sample_rate)
        self._model.generate_audio(self._state, "Hola.")  # calentamiento

    async def load(self) -> None:
        t0 = time.perf_counter()
        try:
            await asyncio.to_thread(self._load)
        except Exception as e:
            raise TTSError(f"no se pudo cargar Pocket TTS: {e}") from e
        log.info("Pocket TTS listo en %.1f s (voz %s)", time.perf_counter() - t0, self.voice)

    async def synthesize(self, text: str) -> Samples:
        chunks = [c async for c in self.stream(text)]
        return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)

    async def stream(self, text: str) -> AsyncIterator[Samples]:
        """Trozos de audio según se generan. Si se deja de leer, la generación se para."""
        if self._model is None:
            raise TTSError("la voz no está cargada")
        text = to_spoken(text)  # «1, 2, 3» → «uno, dos, tres» (la voz lee mal las cifras)
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[Samples | BaseException | None] = asyncio.Queue()
        stop = threading.Event()

        def produce() -> None:
            try:
                for chunk in self._model.generate_audio_stream(self._state, text, stop=stop):
                    if stop.is_set():
                        break
                    audio = chunk.detach().cpu().numpy().reshape(-1).astype(np.float32)
                    loop.call_soon_threadsafe(queue.put_nowait, audio)
            except BaseException as e:  # se entrega al consumidor
                loop.call_soon_threadsafe(queue.put_nowait, e)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        async with self._lock:
            worker = asyncio.create_task(asyncio.to_thread(produce))
            try:
                while (item := await queue.get()) is not None:
                    if isinstance(item, BaseException):
                        raise TTSError(str(item)) from item
                    yield item
            finally:
                stop.set()
                await asyncio.shield(worker)
