"""STTService: whisper-server (whisper.cpp con Vulkan) como proceso residente con el modelo cargado.

- Elige la GPU por nombre: Vulkan también ve la gráfica integrada y el orden puede cambiar.
  Al arrancar lee la lista de dispositivos del registro del servidor y, si el elegido no es
  el que está usando, lo relanza con `--device N`.
- Si el servidor se cae, se relanza en la siguiente petición (máximo 3 fallos seguidos).
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import re
import socket
import subprocess
import sys
import time
import wave
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import httpx
import numpy as np
import numpy.typing as npt

from nyx.audio.capture import SAMPLE_RATE
from nyx.stt.base import STTError

log = logging.getLogger(__name__)

START_TIMEOUT_S = 60.0
REQUEST_TIMEOUT_S = 20.0
MAX_FAILURES = 3

_DEVICE_RE = re.compile(r"ggml_vulkan: (\d+) = (.+?) \((?:[^)]*)\) \| uma: (\d)")


@dataclass(frozen=True, slots=True)
class VulkanDevice:
    index: int
    name: str
    integrated: bool


def parse_devices(lines: list[str]) -> list[VulkanDevice]:
    found: dict[int, VulkanDevice] = {}
    for line in lines:
        if m := _DEVICE_RE.search(line):
            i = int(m.group(1))
            found[i] = VulkanDevice(i, m.group(2).strip(), m.group(3) == "1")
    return [found[i] for i in sorted(found)]


def pick_device(devices: list[VulkanDevice], preferred: str | None) -> VulkanDevice | None:
    """La GPU cuyo nombre contiene `preferred`; si no, la primera dedicada; si no, la primera."""
    if not devices:
        return None
    if preferred:
        for d in devices:
            if preferred.casefold() in d.name.casefold():
                return d
        log.warning("No encuentro la GPU «%s» para whisper.cpp", preferred)
    return next((d for d in devices if not d.integrated), devices[0])


def to_wav(pcm: npt.NDArray[np.int16]) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.astype(np.int16).tobytes())
    return buf.getvalue()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


class WhisperServer:
    def __init__(
        self,
        server: Path,
        model: Path,
        *,
        language: str = "es",
        gpu: str | None = None,
    ) -> None:
        self._server = server
        self._model = model
        self._language = language
        self._gpu = gpu
        self._device: int | None = None
        self._proc: asyncio.subprocess.Process | None = None
        self._reader: asyncio.Task[None] | None = None
        self._log: deque[str] = deque(maxlen=300)
        self._client: httpx.AsyncClient | None = None
        self._failures = 0
        self._lock = asyncio.Lock()
        self.device_name: str | None = None

    async def start(self) -> None:
        async with self._lock:
            if self._device is None:
                devices = await self._probe_devices()
                chosen = pick_device(devices, self._gpu)
                if chosen is not None:
                    self._device = chosen.index
                    self.device_name = chosen.name
            await self._launch()
            devices = parse_devices(list(self._log))
            chosen = pick_device(devices, self._gpu)
            if chosen is None:
                if self.device_name is None:
                    log.warning("whisper.cpp no ve ninguna GPU Vulkan: transcribirá con la CPU")
                return
            if chosen.index != (self._device or 0):
                log.info("Relanzo whisper-server en la GPU %d (%s)", chosen.index, chosen.name)
                self._device = chosen.index
                await self._terminate()
                await self._launch()
            self.device_name = chosen.name
            log.info("whisper.cpp en %s", chosen.name)
        # La primera transcripción prepara la GPU (~250 ms extra): mejor ahora que con el usuario.
        await self.transcribe(np.zeros(SAMPLE_RATE // 2, dtype=np.int16))

    async def _probe_devices(self) -> list[VulkanDevice]:
        """Lista las GPUs Vulkan con `--help` (<0,2 s, sin cargar el modelo en la integrada)."""
        if not self._server.exists():
            return []
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            proc = await asyncio.create_subprocess_exec(
                str(self._server),
                "--help",
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                creationflags=flags,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        except (OSError, TimeoutError):
            return []
        return parse_devices(out.decode("utf-8", errors="replace").splitlines())

    async def stop(self) -> None:
        async with self._lock:
            await self._terminate()

    async def _launch(self) -> None:
        if not self._server.exists():
            raise STTError(f"no existe whisper-server: {self._server}")
        if not self._model.exists():
            raise STTError(f"no existe el modelo de whisper: {self._model}")
        port = _free_port()
        args = [
            str(self._server),
            "-m",
            str(self._model),
            "-l",
            self._language,
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "-nt",
        ]
        if self._device is not None:
            args += ["--device", str(self._device)]
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self._log.clear()
        t0 = time.perf_counter()
        self._proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            creationflags=flags,
        )
        self._reader = asyncio.create_task(self._read_output(self._proc), name="whisper-log")
        self._client = httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{port}", timeout=REQUEST_TIMEOUT_S
        )
        deadline = time.perf_counter() + START_TIMEOUT_S
        while True:
            if self._proc.returncode is not None:
                await asyncio.sleep(0.1)  # deja que el lector recoja las últimas líneas
                tail = "\n".join(list(self._log)[-15:])
                raise STTError(f"whisper-server terminó al arrancar:\n{tail}")
            with contextlib.suppress(httpx.HTTPError):
                if (await self._client.get("/health")).status_code == 200:
                    break
            if time.perf_counter() > deadline:
                raise STTError("whisper-server no responde")
            await asyncio.sleep(0.1)
        log.info("whisper-server listo en %.1f s", time.perf_counter() - t0)

    async def _read_output(self, proc: asyncio.subprocess.Process) -> None:
        assert proc.stdout is not None
        async for raw in proc.stdout:
            line = raw.decode("utf-8", errors="replace").rstrip()
            self._log.append(line)
            log.debug("whisper: %s", line)

    async def _terminate(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        if self._proc is not None and self._proc.returncode is None:
            self._proc.terminate()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._proc.wait(), 5)
        if self._reader is not None:
            self._reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader
        self._proc = None
        self._reader = None

    async def _ensure_running(self) -> httpx.AsyncClient:
        async with self._lock:
            alive = self._proc is not None and self._proc.returncode is None
            if not alive or self._client is None:
                if self._failures >= MAX_FAILURES:
                    raise STTError("whisper-server ha fallado varias veces seguidas")
                log.warning("whisper-server no está en marcha: lo relanzo")
                await self._terminate()
                try:
                    await self._launch()
                except STTError:
                    self._failures += 1
                    raise
            assert self._client is not None
            return self._client

    async def transcribe(self, pcm: npt.NDArray[np.int16], prompt: str = "") -> str:
        client = await self._ensure_running()
        data = {
            "response_format": "json",
            "language": self._language,
            "temperature": "0.0",
            "no_timestamps": "true",
        }
        if prompt:
            data["prompt"] = prompt
        try:
            resp = await client.post(
                "/inference",
                files={"file": ("audio.wav", to_wav(pcm), "audio/wav")},
                data=data,
            )
            resp.raise_for_status()
            text = str(resp.json().get("text", ""))
        except (httpx.HTTPError, ValueError) as e:
            self._failures += 1
            raise STTError(f"fallo al transcribir: {e}") from e
        self._failures = 0
        return text.strip()
