"""Cerebro con llama-server (C5.1): el motor contra un servidor de mentira y el proceso."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from nyx.brain.base import ChatMessage, LLMError, LLMErrorKind, LLMToolCall
from nyx.brain.llamacpp import LlamaCppEngine
from nyx.brain.llamacpp_process import (
    QWEN_TEMPLATE,
    LlamaServer,
    chat_template_for,
    server_args,
)
from nyx.stt.whisper_server import VulkanDevice

MESSAGES = [ChatMessage("system", "Eres Nyx."), ChatMessage("user", "hola")]
URL = "http://llama.test"


class FakeServer:
    """El proceso de llama-server, de mentira: cuenta lanzamientos y paradas."""

    def __init__(self, error: LLMError | None = None) -> None:
        self.error = error
        self.ensured = 0
        self.restarts = 0
        self.stops = 0

    async def ensure(self) -> str:
        self.ensured += 1
        if self.error is not None:
            raise self.error
        return URL

    async def stop(self) -> None:
        self.stops += 1

    async def restart(self) -> None:
        self.restarts += 1


def sse(*chunks: dict[str, Any] | str) -> bytes:
    lines = [f"data: {c if isinstance(c, str) else json.dumps(c)}\n\n" for c in chunks]
    return "".join(lines).encode()


def delta(**fields: Any) -> dict[str, Any]:
    return {"choices": [{"index": 0, "delta": fields}]}


def engine(handler: Any, server: FakeServer | None = None, **kwargs: Any) -> LlamaCppEngine:
    return LlamaCppEngine(
        server or FakeServer(), "nyx-r2:7b", transport=httpx.MockTransport(handler), **kwargs
    )


async def test_stream_with_schema() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        seen.update(json.loads(request.content))
        return httpx.Response(
            200,
            content=sse(delta(content='{"spo'), delta(content='ken": "Hola"}'), "[DONE]"),
        )

    llm = engine(handler, seed=7)
    out = [c async for c in llm.stream(MESSAGES, schema={"type": "object"})]
    assert "".join(out) == '{"spoken": "Hola"}'
    assert seen["stream"] is True
    assert seen["cache_prompt"] is True
    assert seen["seed"] == 7
    assert seen["messages"] == [
        {"role": "system", "content": "Eres Nyx."},
        {"role": "user", "content": "hola"},
    ]
    assert seen["response_format"]["json_schema"]["schema"] == {"type": "object"}
    await llm.aclose()


async def test_tool_calls_arrive_in_pieces() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        first = {"index": 0, "function": {"name": "open_app", "arguments": '{"na'}}
        rest = {"index": 0, "function": {"arguments": 'me": "Steam"}'}}
        second = {"index": 1, "function": {"name": "set_volume", "arguments": '{"level": 30}'}}
        return httpx.Response(
            200,
            content=sse(
                delta(tool_calls=[first]),
                delta(tool_calls=[rest]),
                delta(tool_calls=[second]),
                {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]},
                "[DONE]",
            ),
        )

    tools = [{"type": "function", "function": {"name": "open_app"}}]
    llm = engine(handler)
    out = [p async for p in llm.chat(MESSAGES, tools=tools)]
    assert out == [
        [LLMToolCall("open_app", {"name": "Steam"}), LLMToolCall("set_volume", {"level": 30})]
    ]
    assert seen["tools"] == tools
    await llm.aclose()


async def test_text_answer_without_tools() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=sse(delta(content="Hola"), delta(content="!"), "[DONE]"))

    llm = engine(handler)
    assert [p async for p in llm.chat(MESSAGES)] == ["Hola", "!"]
    await llm.aclose()


async def test_http_error_is_reported() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "context size exceeded"}})

    llm = engine(handler)
    with pytest.raises(LLMError) as exc:
        _ = [p async for p in llm.chat(MESSAGES)]
    assert exc.value.kind is LLMErrorKind.OTHER
    assert "context size" in str(exc.value)
    await llm.aclose()


async def test_error_inside_the_stream() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=sse({"error": {"message": "se acabó la memoria"}}))

    llm = engine(handler)
    with pytest.raises(LLMError, match="memoria"):
        _ = [p async for p in llm.chat(MESSAGES)]
    await llm.aclose()


async def test_relaunches_once_if_it_does_not_answer() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("no responde", request=request)
        return httpx.Response(200, content=sse(delta(content="Ya"), "[DONE]"))

    server = FakeServer()
    llm = engine(handler, server)
    assert [p async for p in llm.chat(MESSAGES)] == ["Ya"]
    assert server.restarts == 1
    assert server.ensured == 2
    await llm.aclose()


async def test_gives_up_after_the_second_try() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no responde", request=request)

    llm = engine(handler)
    with pytest.raises(LLMError) as exc:
        _ = [p async for p in llm.chat(MESSAGES)]
    assert exc.value.kind is LLMErrorKind.UNAVAILABLE
    await llm.aclose()


async def test_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("callado", request=request)

    llm = engine(handler)
    with pytest.raises(LLMError) as exc:
        _ = [p async for p in llm.chat(MESSAGES)]
    assert exc.value.kind is LLMErrorKind.TIMEOUT
    await llm.aclose()


async def test_missing_brain_file() -> None:
    server = FakeServer(LLMError(LLMErrorKind.MODEL_MISSING, "nyx.gguf"))
    llm = engine(lambda _: httpx.Response(500), server)
    with pytest.raises(LLMError) as exc:
        _ = [p async for p in llm.chat(MESSAGES)]
    assert exc.value.kind is LLMErrorKind.MODEL_MISSING
    await llm.aclose()


async def test_warmup_processes_the_prefix_with_one_token() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "H"}}]})

    tools = [{"type": "function", "function": {"name": "open_app"}}]
    llm = engine(handler)
    await llm.warmup([ChatMessage("system", "Eres Nyx.")], tools=tools)
    assert seen["stream"] is False
    assert seen["max_tokens"] == 1
    assert seen["tools"] == tools
    assert seen["messages"][0] == {"role": "system", "content": "Eres Nyx."}
    await llm.aclose()


async def test_unload_stops_the_server() -> None:
    server = FakeServer()
    llm = engine(lambda _: httpx.Response(200), server)
    await llm.unload()
    assert server.stops == 1
    await llm.aclose()


# --- el proceso ---


def test_command_line_on_the_gpu() -> None:
    args = server_args(Path("ls.exe"), Path("nyx.gguf"), 5000, num_ctx=12288, device=1)
    assert args[:3] == ["ls.exe", "-m", "nyx.gguf"]
    joined = " ".join(args)
    assert "--port 5000" in joined
    assert "-c 12288" in joined
    assert "-np 1" in joined  # un solo hueco: todo el contexto y la caché del prefijo
    assert "--jinja" in args
    assert "-ngl 999" in joined
    assert "--device Vulkan1" in joined


def test_command_line_on_the_cpu() -> None:
    args = server_args(Path("ls.exe"), Path("nyx.gguf"), 5000, num_ctx=4096, device=1, cpu=True)
    joined = " ".join(args)
    assert "-ngl 0" in joined
    assert "--device none" in joined
    assert "Vulkan1" not in joined


async def test_missing_server_or_model(tmp_path: Path) -> None:
    model = tmp_path / "nyx.gguf"
    model.write_bytes(b"GGUF")
    with pytest.raises(LLMError) as exc:
        await LlamaServer(tmp_path / "no.exe", model).ensure()
    assert exc.value.kind is LLMErrorKind.UNAVAILABLE

    exe = tmp_path / "llama-server.exe"
    exe.write_bytes(b"")
    with pytest.raises(LLMError) as exc:
        await LlamaServer(exe, tmp_path / "falta.gguf").ensure()
    assert exc.value.kind is LLMErrorKind.MODEL_MISSING


async def test_falls_back_to_the_cpu(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    exe, model = tmp_path / "llama-server.exe", tmp_path / "nyx.gguf"
    exe.write_bytes(b"")
    model.write_bytes(b"GGUF")
    server = LlamaServer(exe, model)
    launched: list[bool] = []

    async def probe() -> list[VulkanDevice]:
        return [VulkanDevice(0, "AMD Radeon(TM) Graphics", True), VulkanDevice(1, "RX", False)]

    async def launch(*, cpu: bool) -> str:
        launched.append(cpu)
        if not cpu:
            raise LLMError(LLMErrorKind.UNAVAILABLE, "vulkan roto")
        return URL

    async def terminate() -> None:
        pass

    monkeypatch.setattr(server, "_probe_devices", probe)
    monkeypatch.setattr(server, "_launch", launch)
    monkeypatch.setattr(server, "_terminate", terminate)
    assert await server._start() == URL
    assert launched == [False, True]
    assert server.on_cpu
    assert server.device_name is None


async def test_picks_the_dedicated_gpu(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    server = LlamaServer(tmp_path / "llama-server.exe", tmp_path / "nyx.gguf")

    async def probe() -> list[VulkanDevice]:
        return [VulkanDevice(0, "AMD Radeon(TM) Graphics", True), VulkanDevice(1, "RX", False)]

    async def launch(*, cpu: bool) -> str:
        return URL

    monkeypatch.setattr(server, "_probe_devices", probe)
    monkeypatch.setattr(server, "_launch", launch)
    await server._start()
    assert server.device_name == "RX"
    assert not server.on_cpu


def test_qwen_template_for_the_nyx_brain() -> None:
    assert chat_template_for("nyx-r2:7b") == QWEN_TEMPLATE
    assert chat_template_for("qwen2.5:7b") == QWEN_TEMPLATE
    assert chat_template_for("gemma4:e4b") is None
    text = QWEN_TEMPLATE.read_text(encoding="utf-8")
    assert "<tool_call>" in text and "<|im_start|>" in text
