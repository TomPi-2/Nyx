import json
from typing import Any

import httpx
import pytest

from nyx.brain.base import ChatMessage, LLMError, LLMErrorKind
from nyx.brain.ollama import OllamaEngine

MESSAGES = [ChatMessage("user", "hola")]


def engine(handler: Any, launcher: Any = None) -> OllamaEngine:
    return OllamaEngine(
        "http://ollama",
        "qwen2.5:7b",
        keep_alive=-1,
        launcher=launcher,
        start_timeout_s=2.0,
        transport=httpx.MockTransport(handler),
    )


def ndjson(*chunks: dict[str, Any]) -> bytes:
    return b"".join(json.dumps(c).encode() + b"\n" for c in chunks)


async def test_stream_yields_content_and_sends_options() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(
            200,
            content=ndjson(
                {"message": {"content": '{"spo'}},
                {"message": {"content": 'ken": "Hola"}'}},
                {"message": {"content": ""}, "done": True},
            ),
        )

    llm = engine(handler)
    out = [c async for c in llm.stream(MESSAGES, schema={"type": "object"})]
    assert "".join(out) == '{"spoken": "Hola"}'
    assert seen["model"] == "qwen2.5:7b"
    assert seen["keep_alive"] == -1
    assert seen["format"] == {"type": "object"}
    assert seen["options"]["num_ctx"] == 4096
    assert seen["messages"] == [{"role": "user", "content": "hola"}]
    await llm.aclose()


async def test_missing_model() -> None:
    llm = engine(lambda _: httpx.Response(404, json={"error": "model not found"}))
    with pytest.raises(LLMError) as exc:
        _ = [c async for c in llm.stream(MESSAGES)]
    assert exc.value.kind is LLMErrorKind.MODEL_MISSING


async def test_server_down() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    llm = engine(handler)
    with pytest.raises(LLMError) as exc:
        _ = [c async for c in llm.stream(MESSAGES)]
    assert exc.value.kind is LLMErrorKind.UNAVAILABLE
    with pytest.raises(LLMError):
        await llm.warmup()


async def test_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    llm = engine(handler)
    with pytest.raises(LLMError) as exc:
        _ = [c async for c in llm.stream(MESSAGES)]
    assert exc.value.kind is LLMErrorKind.TIMEOUT


async def test_error_inside_stream() -> None:
    llm = engine(lambda _: httpx.Response(200, content=ndjson({"error": "boom"})))
    with pytest.raises(LLMError) as exc:
        _ = [c async for c in llm.stream(MESSAGES)]
    assert exc.value.kind is LLMErrorKind.OTHER


async def test_warmup_sends_prefix_with_same_options() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"done": True})

    llm = engine(handler)
    await llm.warmup([ChatMessage("system", "eres Nyx")])
    assert seen["messages"][0] == {"role": "system", "content": "eres Nyx"}
    assert seen["options"]["num_ctx"] == 4096  # igual que en las peticiones: no recarga
    assert seen["options"]["num_predict"] == 1


async def test_connect_timeout_means_not_running() -> None:
    # En Windows, un puerto cerrado tarda ~2 s en rechazar: llega como ConnectTimeout.
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("no", request=request)

    llm = engine(handler)
    with pytest.raises(LLMError) as exc:
        _ = [c async for c in llm.stream(MESSAGES)]
    assert exc.value.kind is LLMErrorKind.UNAVAILABLE


async def test_opens_ollama_and_retries_once() -> None:
    running = {"up": False, "launches": 0}

    def launcher() -> bool:
        running["launches"] += 1
        running["up"] = True
        return True

    def handler(request: httpx.Request) -> httpx.Response:
        if not running["up"]:
            raise httpx.ConnectError("refused", request=request)
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "x"})
        return httpx.Response(200, content=ndjson({"message": {"content": "hola"}, "done": True}))

    llm = engine(handler, launcher)
    assert [c async for c in llm.stream(MESSAGES)] == ["hola"]
    assert running["launches"] == 1


async def test_launch_failure_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    llm = engine(handler, launcher=lambda: False)
    with pytest.raises(LLMError) as exc:
        _ = [c async for c in llm.stream(MESSAGES)]
    assert exc.value.kind is LLMErrorKind.UNAVAILABLE
