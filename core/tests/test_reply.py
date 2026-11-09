import json

import pytest

from nyx.brain.reply import (
    REPLY_SCHEMA,
    BubbleReady,
    ReplyEvent,
    ReplyStreamParser,
    SpokenDelta,
    SpokenEnd,
)

SAMPLE = {"spoken": "En alemán se dice Hallo.", "display": "Hallo", "secondary": "hola · alemán"}


def run(chunks: list[str]) -> tuple[ReplyStreamParser, list[ReplyEvent]]:
    parser = ReplyStreamParser()
    events: list[ReplyEvent] = []
    for chunk in chunks:
        events += parser.feed(chunk)
    return parser, events


def spoken_text(events: list[ReplyEvent]) -> str:
    return "".join(e.text for e in events if isinstance(e, SpokenDelta))


@pytest.mark.parametrize("size", [1, 3, 7, 1000])
def test_any_chunking_gives_same_result(size: int) -> None:
    raw = json.dumps(SAMPLE, ensure_ascii=False)
    parser, events = run([raw[i : i + size] for i in range(0, len(raw), size)])
    assert spoken_text(events) == SAMPLE["spoken"]
    assert [e for e in events if isinstance(e, BubbleReady)] == [
        BubbleReady("Hallo", "hola · alemán")
    ]
    assert sum(isinstance(e, SpokenEnd) for e in events) == 1
    assert parser.finish().model_dump() == SAMPLE


def test_spoken_end_comes_after_last_delta() -> None:
    raw = json.dumps(SAMPLE, ensure_ascii=False)
    _, events = run([raw])
    kinds = [type(e) for e in events]
    assert kinds.index(SpokenEnd) > kinds.index(SpokenDelta)


def test_escapes_and_unicode() -> None:
    value = 'Dice "hola"\nen 2 líneas 🙂 \\ fin'
    raw = json.dumps({"spoken": value, "display": "x", "secondary": "y"})  # ascii: \uXXXX
    parser, events = run([raw[i : i + 2] for i in range(0, len(raw), 2)])
    assert spoken_text(events) == value
    assert parser.finish().spoken == value


def test_truncated_json_keeps_partial_spoken() -> None:
    parser, events = run(['{"spoken": "Hola, esto se co'])
    assert spoken_text(events) == "Hola, esto se co"
    assert parser.finish().spoken == "Hola, esto se co"


def test_bubble_updates_if_display_comes_after_spoken() -> None:
    _, events = run(['{"display": "A", "spoken": "x", "display": "B", "secondary": "c"}'])
    bubbles = [e for e in events if isinstance(e, BubbleReady)]
    assert bubbles[0] == BubbleReady("A", "")
    assert bubbles[-1] == BubbleReady("B", "c")


def test_schema_puts_spoken_first() -> None:
    # La voz empieza antes si `spoken` se genera primero (ver docstring de reply.py).
    assert next(iter(REPLY_SCHEMA["properties"])) == "spoken"
