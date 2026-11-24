"""llama-server (llama.cpp, MIT) como proceso hijo de Nyx con el cerebro cargado (C5.1).

Igual que whisper-server (`nyx/stt/whisper_server.py`): Nyx lo lanza oculto en un puerto
libre, lo vigila y lo relanza si se cae. A diferencia de Ollama, va dentro del grupo de
procesos de Nyx (winjob.py), así que se cierra con ella y no queda nada abierto.

- Elige la GPU por nombre entre las que ve Vulkan (la integrada también sale en la lista):
  las mismas líneas `ggml_vulkan: N = …` que whisper.cpp.
- Un solo hueco (`-np 1`): todo el contexto para una conversación y la caché del prefijo
  (sistema + herramientas) siempre reutilizable.
- Si con la GPU no arranca (controlador antiguo, Vulkan roto…), prueba con el procesador:
  funciona, pero lento. Queda en `on_cpu` para avisar (N-411).
- «Liberar la VRAM» (al salir o en partida con «Solo órdenes») es parar el proceso; la
  siguiente petición lo vuelve a lanzar.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import subprocess
import sys
import time
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from nyx.brain.base import LLMError, LLMErrorKind
from nyx.paths import local_dir
from nyx.stt.whisper_server import VulkanDevice, free_port, parse_devices, pick_device

if TYPE_CHECKING:
    from nyx.settings.model import Settings

log = logging.getLogger(__name__)

#: Cargar ~4,7 GB del disco a la gráfica; con un disco lento, más.
START_TIMEOUT_S = 180.0
MAX_FAILURES = 3


def server_args(
    server: Path,
    model: Path,
    port: int,
    *,
    num_ctx: int,
    device: int | None,
    cpu: bool = False,
    chat_template: Path | None = None,
) -> list[str]:
    """La línea de órdenes de llama-server."""
    args = [
        str(server),
        "-m",
        str(model),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "-c",
        str(num_ctx),
        "-np",
        "1",
        # Plantilla de chat en Jinja (la del GGUF): hace falta para las herramientas.
        "--jinja",
    ]
    if chat_template is not None:
        args += ["--chat-template-file", str(chat_template)]
    if cpu:
        args += ["-ngl", "0", "--device", "none"]
    else:
        args += ["-ngl", "999"]  # el modelo entero en la gráfica
        if device is not None:
            args += ["--device", f"Vulkan{device}"]
    return args


class LlamaServer:
    def __init__(
        self,
        server: Path,
        model: Path,
        *,
        num_ctx: int = 4096,
        gpu: str | None = None,
        chat_template: Path | None = None,
        start_timeout_s: float = START_TIMEOUT_S,
        cpu: bool = False,
    ) -> None:
        """`cpu`: sin gráfica desde el principio (para medirlo en game_bench.py)."""
        self.server = server
        self.model = model
        self._num_ctx = num_ctx
        self._gpu = gpu
        self._chat_template = chat_template
        self._start_timeout_s = start_timeout_s
        self._device: VulkanDevice | None = None
        self._probed = cpu
        self._proc: asyncio.subprocess.Process | None = None
        self._reader: asyncio.Task[None] | None = None
        self._log: deque[str] = deque(maxlen=300)
        self._url: str | None = None
        self._failures = 0
        self._lock = asyncio.Lock()
        self.on_cpu = cpu

    @property
    def device_name(self) -> str | None:
        return None if self.on_cpu or self._device is None else self._device.name

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None and self._url is not None

    async def ensure(self) -> str:
        """La dirección del servidor; lo lanza si no está en marcha. LLMError si no puede."""
        async with self._lock:
            if self.running:
                assert self._url is not None
                return self._url
            if not self.server.is_file():
                raise LLMError(LLMErrorKind.UNAVAILABLE, f"no existe llama-server: {self.server}")
            if not self.model.is_file():
                raise LLMError(LLMErrorKind.MODEL_MISSING, str(self.model))
            if self._failures >= MAX_FAILURES:
                raise LLMError(LLMErrorKind.UNAVAILABLE, "llama-server ha fallado varias veces")
            await self._terminate()
            try:
                self._url = await self._start()
            except LLMError:
                self._failures += 1
                raise
            self._failures = 0
            return self._url

    async def stop(self) -> None:
        async with self._lock:
            await self._terminate()

    async def restart(self) -> None:
        """Para que la siguiente `ensure` lo vuelva a lanzar (no responde aunque siga vivo)."""
        await self.stop()

    async def _start(self) -> str:
        if not self._probed:
            self._probed = True
            devices = await self._probe_devices()
            self._device = pick_device(devices, self._gpu)
            if self._device is None:
                log.warning("llama.cpp no ve ninguna GPU Vulkan: pensará con el procesador")
                self.on_cpu = True
        if not self.on_cpu:
            try:
                url = await self._launch(cpu=False)
                log.info("Cerebro (llama.cpp) en %s", self.device_name)
                return url
            except LLMError as e:
                log.warning("N-411: llama-server no arranca en la GPU (%s); pruebo la CPU", e)
                await self._terminate()
                self.on_cpu = True
        url = await self._launch(cpu=True)
        log.warning("N-411: el cerebro (llama.cpp) va con el procesador: responderá lento")
        return url

    async def _probe_devices(self) -> list[VulkanDevice]:
        """Las GPU que ve Vulkan, sin cargar el modelo (`--list-devices`, ~1 s). Con `-v`
        salen las líneas `ggml_vulkan: N = … | uma: 1` (uma = integrada); N es el de
        `--device VulkanN`."""
        try:
            proc = await asyncio.create_subprocess_exec(
                str(self.server),
                "-v",
                "--list-devices",
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                creationflags=_NO_WINDOW,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=15.0)
        except OSError, TimeoutError:
            return []
        return parse_devices(out.decode("utf-8", errors="replace").splitlines())

    async def _launch(self, *, cpu: bool) -> str:
        port = free_port()
        args = server_args(
            self.server,
            self.model,
            port,
            num_ctx=self._num_ctx,
            device=None if self._device is None else self._device.index,
            cpu=cpu,
            chat_template=self._chat_template,
        )
        self._log.clear()
        t0 = time.perf_counter()
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                creationflags=_NO_WINDOW,
                # En su carpeta, por sus DLL (ggml-vulkan.dll…) y para no bloquear la de Nyx.
                cwd=self.server.parent,
            )
        except OSError as e:
            raise LLMError(LLMErrorKind.UNAVAILABLE, f"no se pudo lanzar llama-server: {e}") from e
        self._reader = asyncio.create_task(self._read_output(self._proc), name="llama-log")
        url = f"http://127.0.0.1:{port}"
        deadline = time.perf_counter() + self._start_timeout_s
        async with httpx.AsyncClient(timeout=2.0) as http:
            while True:
                if self._proc.returncode is not None:
                    await asyncio.sleep(0.1)  # deja que el lector recoja las últimas líneas
                    tail = "\n".join(list(self._log)[-15:])
                    raise LLMError(LLMErrorKind.UNAVAILABLE, f"llama-server terminó:\n{tail}")
                # /health da 503 mientras carga el modelo y 200 cuando ya puede responder.
                with contextlib.suppress(httpx.HTTPError):
                    if (await http.get(f"{url}/health")).status_code == 200:
                        break
                if time.perf_counter() > deadline:
                    raise LLMError(LLMErrorKind.UNAVAILABLE, "llama-server no responde")
                await asyncio.sleep(0.2)
        log.info("llama-server listo en %.1f s", time.perf_counter() - t0)
        return url

    async def _read_output(self, proc: asyncio.subprocess.Process) -> None:
        assert proc.stdout is not None
        async for raw in proc.stdout:
            line = raw.decode("utf-8", errors="replace").rstrip()
            self._log.append(line)
            log.debug("llama: %s", line)

    async def _terminate(self) -> None:
        self._url = None
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


_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def server_path(settings: Settings) -> Path:
    r"""Como el de whisper: el de los ajustes, el que va con Nyx (`core\bin\llama`, junto a
    su Python) o el de %LOCALAPPDATA%\Nyx\llama."""
    if settings.llm.server is not None:
        return settings.llm.server
    packaged = Path(sys.prefix).parent / "bin" / "llama" / "llama-server.exe"
    if packaged.is_file():
        return packaged
    return local_dir() / "llama" / "llama-server.exe"


def from_settings(
    settings: Settings, *, num_ctx: int | None = None, cpu: bool = False
) -> LlamaServer:
    """El servidor con el cerebro de los ajustes (por defecto, el bajado en el primer
    arranque) y la GPU de whisper si no se elige otra."""
    from nyx.setup.brain import gguf_path

    return LlamaServer(
        server_path(settings),
        settings.llm.model_path or gguf_path(),
        num_ctx=num_ctx or settings.llm.num_ctx,
        gpu=settings.llm.gpu or settings.stt.gpu,
        chat_template=chat_template_for(settings.llm.model),
        cpu=cpu,
    )


def chat_template_for(model: str) -> Path | None:
    """La plantilla oficial de Qwen 2.5 (Apache-2.0, de su tokenizer_config.json) para el
    cerebro de Nyx y Qwen 2.5: con ella llama.cpp reconoce el formato de las herramientas
    (`<tool_call>`) aunque el GGUF no traiga plantilla (el de Nyx se hizo para Ollama, que
    pone la suya). Para otros modelos, la que traiga su GGUF."""
    if model.startswith(("nyx-", "qwen2.5")):
        return QWEN_TEMPLATE
    return None


QWEN_TEMPLATE = Path(__file__).resolve().parent / "data" / "qwen2.5.jinja"
