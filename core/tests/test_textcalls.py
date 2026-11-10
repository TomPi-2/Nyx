from collections.abc import AsyncIterator, Sequence
from typing import Any

import pytest

from nyx.brain.base import ChatMessage, LLMToolCall
from nyx.brain.reply import SpokenDelta
from nyx.brain.service import Brain, ReplyDone, ToolPlan
from nyx.brain.textcalls import could_be_call, parse_text_calls

NAMES = ["close_app", "open_app", "set_volume"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('close_app({"name": "Spotify"})', [LLMToolCall("close_app", {"name": "Spotify"})]),
        (
            'openapp(name="Bloc de notas")\nsetvolume(level=20)',
            [
                LLMToolCall("open_app", {"name": "Bloc de notas"}),
                LLMToolCall("set_volume", {"level": 20}),
            ],
        ),
        (
            '{"name": "close_app", "arguments": {"name": null}}',
            [LLMToolCall("close_app", {"name": None})],
        ),
        (
            '<tool_call>\n{"name": "set_volume", "arguments": {"level": 20}}\n</tool_call>',
            [LLMToolCall("set_volume", {"level": 20})],
        ),
        ('close_app({"name": null})', [LLMToolCall("close_app", {"name": None})]),
        ("`close_app(name='Discord')`", [LLMToolCall("close_app", {"name": "Discord"})]),
    ],
)
def test_parse_written_calls(text: str, expected: list[LLMToolCall]) -> None:
    assert parse_text_calls(text, NAMES) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Vale",
        "Son las siete.",
        'borrar_todo({"x": 1})',  # no es una herramienta
        'close_app({"name": "Spotify"})\ny ya está',  # mezcla con texto
        "close_app(__import__('os'))",  # nada que no sea un literal
    ],
)
def test_not_calls(text: str) -> None:
    assert parse_text_calls(text, NAMES) == []


def test_could_be_call() -> None:
    assert could_be_call("close_app(", NAMES)
    assert could_be_call("closeapp (", NAMES)
    assert could_be_call('{"name"', NAMES)
    assert not could_be_call("Son las", NAMES)
    assert not could_be_call("borrar(", NAMES)


class ScriptedLLM:
    def __init__(self, chunks: list[str]) -> None:
        self.chunks = chunks

    async def warmup(
        self, prefix: Sequence[ChatMessage] = (), *, tools: Sequence[dict[str, Any]] = ()
    ) -> None:
        pass

    async def unload(self) -> None:
        pass

    async def stream(
        self, messages: Sequence[ChatMessage], *, schema: dict[str, Any] | None = None
    ) -> AsyncIterator[str]:
        for c in self.chunks:
            yield c

    async def chat(
        self, messages: Sequence[ChatMessage], *, tools: Sequence[dict[str, Any]] = ()
    ) -> AsyncIterator[str | list[LLMToolCall]]:
        for c in self.chunks:
            yield c


TOOLS = [{"type": "function", "function": {"name": n}} for n in NAMES]


async def collect(chunks: list[str]) -> list[object]:
    brain = Brain(ScriptedLLM(chunks), tools=TOOLS)
    return [e async for e in brain.respond("x")]


async def test_written_call_becomes_a_plan_and_is_not_spoken() -> None:
    events = await collect(["close", "_app", '({"name": ', '"Spotify"})'])
    assert not [e for e in events if isinstance(e, SpokenDelta)]
    assert events[-1] == ToolPlan([LLMToolCall("close_app", {"name": "Spotify"})])


@pytest.mark.parametrize(
    "chunks",
    [["[Hallo | hola]\n", "En alemán se dice Hallo."], ["Son", " las siete."], ["Vale"]],
)
async def test_normal_text_still_streams(chunks: list[str]) -> None:
    events = await collect(chunks)
    spoken = "".join(e.text for e in events if isinstance(e, SpokenDelta))
    assert spoken == "".join(chunks).split("\n")[-1]
    assert isinstance(events[-1], ReplyDone)


async def test_written_call_after_a_header_line() -> None:
    """Lo que pasó en la prueba real: «[acciones]» y debajo la llamada."""
    events = await collect(["[acciones]", "\n", "closeapp(", '{"name": "Spotify"})'])
    assert not [e for e in events if isinstance(e, SpokenDelta)]
    assert events[-1] == ToolPlan([LLMToolCall("close_app", {"name": "Spotify"})])


def test_spaced_written_call() -> None:
    calls = parse_text_calls('mediacontrol {"action": "playpause"}', ["media_control"])
    assert calls == [LLMToolCall("media_control", {"action": "playpause"})]
