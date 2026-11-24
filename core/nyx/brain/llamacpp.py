"""Cerebro nivel 2 sin Ollama: llama-server (llama.cpp) por su API compatible con OpenAI (C5.1).

Misma interfaz que `OllamaEngine` (`nyx/brain/base.py`), así que el resto de Nyx no cambia.
Diferencias con Ollama:

- El servidor lo lanza Nyx (`LlamaServer`) y se cierra con ella; no hay que instalar nada.
- El tamaño del contexto se fija al lanzar el servidor, no en cada petición.
- La respuesta llega como eventos SSE (`data: {...}`), y las llamadas a herramientas llegan
  a trozos (nombre primero, argumentos en varias partes): se juntan y se dan al final.
- Salida con esquema JSON por gramática: nunca sale mal formada.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Sequence
from typing import Any, Protocol

import httpx

from nyx.brain.base import ChatMessage, LLMError, LLMErrorKind, LLMToolCall
from nyx.brain.ollama import parse_tool_call

log = logging.getLogger(__name__)

_CONNECT_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout)


class Server(Protocol):
    """Lo que el motor necesita del proceso (`LlamaServer`; en las pruebas, uno de mentira)."""

    async def ensure(self) -> str: ...

    async def stop(self) -> None: ...

    async def restart(self) -> None: ...


class _NotRunningError(Exception):
    pass


class _ToolCalls:
    """Junta las llamadas que llegan a trozos (`delta.tool_calls[i]`) por su índice."""

    def __init__(self) -> None:
        self._calls: dict[int, dict[str, str]] = {}

    def add(self, deltas: list[dict[str, Any]]) -> None:
        for n, delta in enumerate(deltas):
            index = int(delta.get("index", n))
            call = self._calls.setdefault(index, {"name": "", "arguments": ""})
            function = delta.get("function") or {}
            call["name"] += str(function.get("name") or "")
            arguments = function.get("arguments")
            if isinstance(arguments, dict):  # por si llega ya como objeto
                arguments = json.dumps(arguments)
            call["arguments"] += str(arguments or "")

    def done(self) -> list[LLMToolCall]:
        return [
            parse_tool_call({"function": self._calls[i]})
            for i in sorted(self._calls)
            if self._calls[i]["name"]
        ]


class LlamaCppEngine:
    def __init__(
        self,
        server: Server,
        model: str,
        *,
        timeout_s: float = 8.0,
        temperature: float = 0.3,
        seed: int | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.server = server
        self.model = model  # solo para el registro y los datos de uso
        self._temperature = temperature
        self.seed = seed
        # `read` se aplica a cada trozo: si el modelo se queda callado más de timeout_s, se corta.
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s, connect=3.0), transport=transport
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _body(self, messages: Sequence[ChatMessage]) -> dict[str, Any]:
        body: dict[str, Any] = {
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            "temperature": self._temperature,
            # Reutiliza lo ya procesado del principio del prompt (sistema + herramientas).
            "cache_prompt": True,
        }
        if self.seed is not None:
            body["seed"] = self.seed
        return body

    async def warmup(
        self, prefix: Sequence[ChatMessage] = (), *, tools: Sequence[dict[str, Any]] = ()
    ) -> None:
        # Lanza el servidor (carga el modelo) y procesa el prefijo fijo con 1 token de salida:
        # la primera petición real lo encuentra en la caché.
        body = self._body([*prefix, ChatMessage("user", "Hola")])
        body.update(stream=False, max_tokens=1)
        if tools:
            body["tools"] = list(tools)
        for attempt in (1, 2):
            url = await self.server.ensure()
            try:
                resp = await self._client.post(
                    f"{url}/v1/chat/completions", json=body, timeout=120.0
                )
            except _CONNECT_ERRORS as e:
                if attempt == 1:
                    await self.server.restart()
                    continue
                raise LLMError(LLMErrorKind.UNAVAILABLE, str(e)) from e
            except httpx.HTTPError as e:
                raise LLMError(LLMErrorKind.UNAVAILABLE, str(e)) from e
            _check(resp)
            return

    async def unload(self) -> None:
        """Libera la VRAM: para el servidor (vuelve a lanzarse en la siguiente petición)."""
        try:
            await self.server.stop()
        except Exception:
            log.debug("No se pudo parar llama-server", exc_info=True)

    async def stream(
        self, messages: Sequence[ChatMessage], *, schema: dict[str, Any] | None = None
    ) -> AsyncIterator[str]:
        body = self._body(messages)
        if schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "respuesta", "schema": schema},
            }
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
            url = await self.server.ensure()
            try:
                async for piece in self._stream_once(url, body):
                    yield piece
                return
            except _NotRunningError as e:
                if attempt == 1:
                    log.warning("llama-server no responde: lo relanzo")
                    await self.server.restart()
                    continue
                raise LLMError(LLMErrorKind.UNAVAILABLE, str(e.__cause__)) from e

    async def _stream_once(
        self, url: str, body: dict[str, Any]
    ) -> AsyncIterator[str | list[LLMToolCall]]:
        calls = _ToolCalls()
        try:
            async with self._client.stream("POST", f"{url}/v1/chat/completions", json=body) as resp:
                if resp.status_code >= 400:
                    await resp.aread()
                    _check(resp)
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue  # líneas vacías y comentarios de SSE
                    data = line.removeprefix("data:").strip()
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    if "error" in chunk:
                        raise LLMError(LLMErrorKind.OTHER, _error_text(chunk["error"]))
                    for choice in chunk.get("choices", []):
                        delta = choice.get("delta") or {}
                        if content := delta.get("content"):
                            yield str(content)
                        if deltas := delta.get("tool_calls"):
                            calls.add(list(deltas))
        # La conexión solo puede fallar antes del primer trozo: reintentar es seguro.
        except _CONNECT_ERRORS as e:
            raise _NotRunningError() from e
        except httpx.TimeoutException as e:
            raise LLMError(LLMErrorKind.TIMEOUT, str(e)) from e
        except httpx.HTTPError as e:
            raise LLMError(LLMErrorKind.UNAVAILABLE, str(e)) from e
        except json.JSONDecodeError as e:
            raise LLMError(LLMErrorKind.OTHER, "respuesta no válida") from e
        if done := calls.done():
            yield done


def _error_text(error: Any) -> str:
    if isinstance(error, dict):
        return str(error.get("message") or error)
    return str(error)


def _check(resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    try:
        detail = _error_text(resp.json().get("error", resp.text))
    except ValueError:
        detail = resp.text
    raise LLMError(LLMErrorKind.OTHER, f"HTTP {resp.status_code}: {detail[:300]}")
