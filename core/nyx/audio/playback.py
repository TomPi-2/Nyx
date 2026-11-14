"""Reproducción de la voz de Nyx: cola de fragmentos, corte inmediato y nivel para el indicador.

El stream de salida solo está abierto mientras Nyx habla (0 % de CPU en reposo).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import threading
from collections import deque
from typing import Any

import numpy as np
import numpy.typing as npt

from nyx.audio import devices

log = logging.getLogger(__name__)

Samples = npt.NDArray[np.float32]
BLOCK = 480  # 20 ms a 24 kHz


class Player:
    def __init__(self, sample_rate: int, device: str | None = None) -> None:
        self.sample_rate = sample_rate
        self._device_name = device
        self._chunks: deque[Samples] = deque()
        self._offset = 0
        self._lock = threading.Lock()
        self._level = 0.0
        self._stream: Any = None
        # Se activa (desde el hilo de audio) cuando la cola se queda vacía.
        self._idle = asyncio.Event()
        self._idle.set()
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def level(self) -> float:
        """Nivel 0–1 del último bloque reproducido."""
        return self._level

    @property
    def busy(self) -> bool:
        with self._lock:
            return bool(self._chunks)

    @property
    def queued_s(self) -> float:
        """Lo que falta por sonar de lo encolado, en segundos (6.28: cuándo empieza una frase)."""
        with self._lock:
            samples = sum(int(c.shape[0]) for c in self._chunks) - self._offset
        return max(0, samples) / self.sample_rate

    def enqueue(self, samples: Samples) -> None:
        if samples.size == 0:
            return
        self._loop = asyncio.get_running_loop()
        with self._lock:
            self._chunks.append(samples.astype(np.float32, copy=False))
            self._idle.clear()
        self._ensure_stream()

    def prepare(self) -> None:
        """Abre el dispositivo de salida por adelantado (tarda ~100 ms) mientras se sintetiza."""
        self._ensure_stream()

    def fade_out(self, ms: float = 150.0) -> None:
        """Calla la voz con un fundido corto (sin el chasquido de cortar en seco) y tira lo
        que quede. Lo usa el primer arranque al pasar de paso mientras Nyx habla."""
        with self._lock:
            if not self._chunks:
                return
            # Lo que iba a sonar en los próximos `ms`, bajando hasta 0; lo demás se tira. Lo
            # que se encole después (la frase siguiente) suena entero tras el fundido.
            need = max(1, int(self.sample_rate * ms / 1000))
            parts: list[Samples] = []
            for i, chunk in enumerate(self._chunks):
                start = self._offset if i == 0 else 0
                part = chunk[start : start + need]
                parts.append(part)
                need -= int(part.shape[0])
                if need <= 0:
                    break
            tail = np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
            tail = tail * np.linspace(1.0, 0.0, tail.shape[0], dtype=np.float32)
            self._chunks.clear()
            self._offset = 0
            if tail.size:
                self._chunks.append(tail.astype(np.float32, copy=False))
            else:
                self._idle.set()

    def clear(self) -> None:
        """Corta la voz al instante (interrupción o nueva petición)."""
        with self._lock:
            self._chunks.clear()
            self._offset = 0
            self._idle.set()
        self._level = 0.0
        self.close()

    async def drain(self) -> None:
        """Espera a que termine de sonar todo lo encolado y cierra el stream."""
        await self._idle.wait()
        # Lo que queda en el búfer del dispositivo (~1 bloque y la latencia de salida).
        await asyncio.sleep(0.12)
        self._level = 0.0
        self.close()

    def close(self) -> None:
        if self._stream is not None:
            with contextlib.suppress(Exception):
                self._stream.stop()
                self._stream.close()
            self._stream = None

    def _ensure_stream(self) -> None:
        if self._stream is not None:
            return
        import sounddevice as sd

        index, extra = devices.resolve("output", self._device_name)
        self._stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=BLOCK,
            device=index,
            extra_settings=extra,
            callback=self._callback,
        )
        self._stream.start()

    def _callback(self, outdata: Any, frames: int, _time: Any, status: Any) -> None:
        block = self.fill(frames)
        outdata[:, 0] = block

    def fill(self, frames: int) -> Samples:
        """Saca `frames` muestras de la cola (con silencio si no hay bastantes)."""
        out = np.zeros(frames, dtype=np.float32)
        pos = 0
        with self._lock:
            had_audio = bool(self._chunks)
            while pos < frames and self._chunks:
                chunk = self._chunks[0]
                take = min(frames - pos, chunk.shape[0] - self._offset)
                out[pos : pos + take] = chunk[self._offset : self._offset + take]
                pos += take
                self._offset += take
                if self._offset >= chunk.shape[0]:
                    self._chunks.popleft()
                    self._offset = 0
            if had_audio and not self._chunks and self._loop is not None:
                self._loop.call_soon_threadsafe(self._idle.set)
        rms = math.sqrt(float(np.mean(np.square(out)))) if frames else 0.0
        self._level = min(1.0, rms * 4.0)
        return out
