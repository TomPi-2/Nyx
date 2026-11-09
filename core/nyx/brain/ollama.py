"""Cerebro nivel 2: Ollama por su API HTTP local, con la respuesta en streaming.

Si Ollama no está en marcha, se abre y se repite la petición una vez (SPEC sección 14:
un supervisor reinicia los servicios que caen). En Windows, conectar a un puerto cerrado
tarda ~2 s (reintentos de TCP), así que un «connect timeout» también significa «no está».
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from collections.abc import AsyncIterator, Callable, Sequence
from pathlib import Path
from typing import Any

import httpx

from nyx.brain.base import ChatMessage, LLMError, LLMErrorKind, LLMToolCall

log = logging.getLogger(__name__)

START_TIMEOUT_S = 20.0
# Si ya se intentó abrir hace poco, no se vuelve a lanzar: solo se espera.
RELAUNCH_AFTER_S = 60.0

_CONNECT_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout)


class _NotRunningError(Exception):
    pass


def ollama_command() -> list[str] | None:
    """La app de Ollama (bandeja + servidor) o, si no está, `ollama serve`."""
    local = os.environ.get("LOCALAPPDATA")
    candidates = [Path(local) / "Programs" / "Ollama"] if local else []
    if exe := shutil.which("ollama"):
        candidates.append(Path(exe).parent)
    for folder in candidates:
        if (app := folder / "ollama app.exe").exists():
            return [str(app)]
    if exe:
        return [exe, "serve"]
    return None


def launch_ollama() -> bool:
    """Abre Ollama como proceso independiente: sigue vivo aunque Nyx se cierre."""
    cmd = ollama_command()
    if cmd is None:
        log.warning("No encuentro Ollama instalado")
        return False
    if sys.platform != "win32":
        subprocess.Popen(cmd, start_new_session=True)
        return True
    base = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    # Fuera del job object de Nyx (ver winjob.py) para no cerrarlo al salir de Nyx.
    for flags in (base | subprocess.CREATE_BREAKAWAY_FROM_JOB, base):
        try:
            subprocess.Popen(
                cmd,
                creationflags=flags,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            log.info("Abriendo Ollama: %s", cmd[0])
            return True
        except OSError:
            continue
    log.warning("No se pudo abrir Ollama", exc_info=True)
    return False


def parse_tool_call(raw: dict[str, Any]) -> LLMToolCall:
    function = raw.get("function", {})
    arguments = function.get("arguments") or {}
    if isinstance(arguments, str):  # algunos modelos devuelven el JSON como texto
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            arguments = {}
    return LLMToolCall(str(function.get("name", "")), dict(arguments))


class OllamaEngine:
    def __init__(
        self,
        host: str,
        model: str,
        *,
        keep_alive: int | str = -1,
        num_ctx: int = 4096,
        timeout_s: float = 8.0,
        temperature: float = 0.3,
        launcher: Callable[[], bool] | None = None,
        start_timeout_s: float = START_TIMEOUT_S,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        self._keep_alive = keep_alive
        self._options = {"num_ctx": num_ctx, "temperature": temperature}
        self._launcher = launcher
        self._start_timeout_s = start_timeout_s
        self._launched_at: float | None = None
        # `read` se aplica a cada trozo: si el modelo se queda callado más de timeout_s, se corta.
        self._client = httpx.AsyncClient(
            base_url=host,
            timeout=httpx.Timeout(timeout_s, connect=3.0),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _recover(self) -> bool:
        """Abre Ollama (si no se hizo hace poco) y espera a que responda."""
        if self._launcher is None:
            return False
        now = time.monotonic()
        if self._launched_at is None or now - self._launched_at > RELAUNCH_AFTER_S:
            log.warning("Ollama no responde: intento abrirlo")
            if not await asyncio.to_thread(self._launcher):
                return False
            self._launched_at = now
        deadline = now + self._start_timeout_s
        while time.monotonic() < deadline:
            try:
                if (await self._client.get("/api/version", timeout=1.0)).status_code == 200:
                    log.info("Ollama ya responde")
                    return True
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.5)
        return False

    async def warmup(
        self, prefix: Sequence[ChatMessage] = (), *, tools: Sequence[dict[str, Any]] = ()
    ) -> None:
        # Carga el modelo y procesa el prefijo fijo del prompt con 1 token de salida: la
        # primera petición real reutiliza ese prefijo de la caché. Mismas opciones que en
        # las peticiones (un num_ctx distinto obligaría a recargar el modelo).
        body: dict[str, Any] = {
            "model": self.model,
            "stream": False,
            "keep_alive": self._keep_alive,
            "options": {**self._options, "num_predict": 1},
            "messages": [{"role": m.role, "content": m.content} for m in prefix]
            + [{"role": "user", "content": "Hola"}],
        }
        if tools:
            body["tools"] = list(tools)
        for attempt in (1, 2):
            try:
                resp = await self._client.post("/api/chat", json=body, timeout=120.0)
            except _CONNECT_ERRORS as e:
                if attempt == 1 and await self._recover():
                    continue
                raise LLMError(LLMErrorKind.UNAVAILABLE, str(e)) from e
            except httpx.HTTPError as e:
                raise LLMError(LLMErrorKind.UNAVAILABLE, str(e)) from e
            self._check(resp)
            return

    async def unload(self) -> None:
        try:
            await self._client.post(
                "/api/generate", json={"model": self.model, "keep_alive": 0}, timeout=5.0
            )
        except httpx.HTTPError:
            log.debug("No se pudo descargar el modelo de Ollama", exc_info=True)

    def _check(self, resp: httpx.Response) -> None:
        if resp.status_code == 404:
            raise LLMError(LLMErrorKind.MODEL_MISSING, self.model)
        if resp.status_code >= 400:
            raise LLMError(LLMErrorKind.OTHER, f"HTTP {resp.status_code}")

    def _body(self, messages: Sequence[ChatMessage]) -> dict[str, Any]:
        return {
            "model": self.model,
            "stream": True,
            "keep_alive": self._keep_alive,
            "options": self._options,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }

    async def stream(
        self, messages: Sequence[ChatMessage], *, schema: dict[str, Any] | None = None
    ) -> AsyncIterator[str]:
        body = self._body(messages)
        if schema is not None:
            body["format"] = schema
        async for piece in self._with_recovery(body):
            if isinstance(piece, str):
                yield piece

    async def chat(
        self, messages: Sequence[ChatMessage], *, tools: Sequence[dict[str, Any]] = ()
    ) -> AsyncIterator[str | list[LLMToolCall]]:
        """Texto a trozos o, si el modelo decide actuar, la lista de llamadas a herramientas."""
        body = self._body(messages)
        if tools:
            body["tools"] = list(tools)
        async for piece in self._with_recovery(body):
            yield piece

    async def _with_recovery(self, body: dict[str, Any]) -> AsyncIterator[str | list[LLMToolCall]]:
        for attempt in (1, 2):
            try:
                async for piece in self._stream_once(body):
                    yield piece
                return
            except _NotRunningError as e:
                if attempt == 1 and await self._recover():
                    continue
                raise LLMError(LLMErrorKind.UNAVAILABLE, str(e.__cause__)) from e

    async def _stream_once(self, body: dict[str, Any]) -> AsyncIterator[str | list[LLMToolCall]]:
        try:
            async with self._client.stream("POST", "/api/chat", json=body) as resp:
                if resp.status_code >= 400:
                    await resp.aread()
                    self._check(resp)
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    if "error" in chunk:
                        raise LLMError(LLMErrorKind.OTHER, str(chunk["error"]))
                    message = chunk.get("message", {})
                    if content := message.get("content", ""):
                        yield content
                    if calls := message.get("tool_calls"):
                        yield [parse_tool_call(c) for c in calls]
                    if chunk.get("done"):
                        return
        # La conexión solo puede fallar antes del primer trozo: reintentar es seguro.
        except _CONNECT_ERRORS as e:
            raise _NotRunningError() from e
        except httpx.TimeoutException as e:
            raise LLMError(LLMErrorKind.TIMEOUT, str(e)) from e
        except httpx.HTTPError as e:
            raise LLMError(LLMErrorKind.UNAVAILABLE, str(e)) from e
        except json.JSONDecodeError as e:
            raise LLMError(LLMErrorKind.OTHER, "respuesta no válida") from e
