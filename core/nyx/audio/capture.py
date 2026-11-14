"""AudioService: micrófono a 16 kHz mono en bloques de 32 ms con búfer de pre-grabación.

El callback de PortAudio corre en otro hilo: solo copia el bloque y lo pasa al bucle de
asyncio. Todo el procesado (activación, VAD) ocurre en el bucle.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
from collections import deque
from collections.abc import AsyncIterator
from typing import Any

import numpy as np
import numpy.typing as npt

from nyx.audio import devices

log = logging.getLogger(__name__)

SAMPLE_RATE = 16_000
FRAME_SAMPLES = 512  # 32 ms: el tamaño que espera Silero VAD
FRAME_S = FRAME_SAMPLES / SAMPLE_RATE
QUEUE_FRAMES = 200  # ~6 s: si el bucle se atasca más, se descartan los más antiguos
STALL_S = 2.0  # sin audio durante este tiempo → reabrir el micrófono

Frame = npt.NDArray[np.int16]


def rms_level(frame: Frame) -> float:
    """Nivel 0–1 para el indicador: −55 dBFS → 0, −10 dBFS → 1."""
    if frame.size == 0:
        return 0.0
    rms = math.sqrt(float(np.mean(np.square(frame.astype(np.float32))))) / 32768.0
    db = 20.0 * math.log10(rms + 1e-9)
    return min(1.0, max(0.0, (db + 55.0) / 45.0))


class AudioCapture:
    def __init__(self, device: str | None = None, prebuffer_s: float = 2.0) -> None:
        self._device_name = device
        self._ring: deque[Frame] = deque(maxlen=max(1, math.ceil(prebuffer_s / FRAME_S)))
        self._queue: asyncio.Queue[Frame] = asyncio.Queue(maxsize=QUEUE_FRAMES)
        self._stream: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._last_frame = 0.0

    def start(self) -> None:
        import sounddevice as sd

        self._loop = asyncio.get_running_loop()
        index, extra = devices.resolve("input", self._device_name)
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=FRAME_SAMPLES,
            device=index,
            extra_settings=extra,
            callback=self._callback,
        )
        self._stream.start()
        self._last_frame = self._loop.time()

    def stop(self) -> None:
        if self._stream is not None:
            with contextlib.suppress(Exception):
                self._stream.stop()
                self._stream.close()
            self._stream = None

    def switch(self, device: str | None) -> None:
        """Cambia de micrófono sin parar Nyx (primer arranque: el elegido se usa ya)."""
        self.stop()
        self._device_name = device
        self._ring.clear()
        self.start()

    def _callback(self, indata: Any, frames: int, _time: Any, status: Any) -> None:
        if status:
            log.debug("Micrófono: %s", status)
        frame: Frame = np.array(indata[:, 0], dtype=np.int16, copy=True)
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._push, frame)

    def _push(self, frame: Frame) -> None:
        if self._queue.full():
            self._queue.get_nowait()
        self._queue.put_nowait(frame)

    async def frames(self) -> AsyncIterator[Frame]:
        """Bloques del micrófono. Si el dispositivo deja de dar audio, lo reabre."""
        while True:
            try:
                frame = await asyncio.wait_for(self._queue.get(), STALL_S)
            except TimeoutError:
                log.warning("El micrófono no da audio: lo reabro con el predeterminado")
                self.stop()
                self._device_name = None
                await asyncio.sleep(0.5)
                try:
                    self.start()
                except Exception:
                    log.exception("No se pudo reabrir el micrófono")
                    await asyncio.sleep(STALL_S)
                continue
            self._ring.append(frame)
            yield frame

    def prebuffer(self, seconds: float) -> list[Frame]:
        """Los últimos `seconds` de audio (incluido el bloque actual)."""
        n = math.ceil(seconds / FRAME_S)
        return list(self._ring)[-n:] if n > 0 else []
