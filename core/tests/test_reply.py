import pytest

from nyx.brain.reply import (
    BubbleReady,
    ReplyEvent,
    SpokenDelta,
    SpokenEnd,
    TextReplyParser,
    first_sentence,
)

SAMPLE = "[Hallo | hola · alemán]\nEn alemán se dice Hallo."


def run(chunks: list[str]) -> tuple[list[ReplyEvent], TextReplyParser]:
    parser = TextReplyParser()
    events: list[ReplyEvent] = []
    for chunk in chunks:
        events += parser.feed(chunk)
    tail, reply = parser.finish()
    events += tail
    parser.reply = reply  # type: ignore[attr-defined]
    return events, parser


def spoken(events: list[ReplyEvent]) -> str:
    return "".join(e.text for e in events if isinstance(e, SpokenDelta))


@pytest.mark.parametrize("size", [1, 3, 7, 1000])
def test_header_and_spoken_with_any_chunking(size: int) -> None:
    events, parser = run([SAMPLE[i : i + size] for i in range(0, len(SAMPLE), size)])
    assert [e for e in events if isinstance(e, BubbleReady)] == [
        BubbleReady("Hallo", "hola · alemán")
    ]
    assert spoken(events) == "En alemán se dice Hallo."
    assert isinstance(events[-1], SpokenEnd)
    reply = parser.reply  # type: ignore[attr-defined]
    assert (reply.display, reply.secondary, reply.spoken) == (
        "Hallo",
        "hola · alemán",
        "En alemán se dice Hallo.",
    )


def test_bubble_comes_before_any_speech() -> None:
    events, _ = run([SAMPLE])
    kinds = [type(e) for e in events]
    assert kinds.index(BubbleReady) < kinds.index(SpokenDelta)


def test_without_header_everything_is_spoken() -> None:
    events, parser = run(["Son las siete y cuarto. ", "Buenas tardes."])
    assert spoken(events) == "Son las siete y cuarto. Buenas tardes."
    assert parser.reply.display == "Son las siete y cuarto."  # type: ignore[attr-defined]


def test_header_without_secondary_and_markdown() -> None:
    events, parser = run(["[18 °C]\n**Hace** 18 grados."])
    assert parser.reply.display == "18 °C" and parser.reply.secondary == ""  # type: ignore[attr-defined]
    assert spoken(events) == "Hace 18 grados."


def test_unclosed_bracket_is_spoken() -> None:
    events, _ = run(["[esto no se cierra " + "x" * 200])
    assert spoken(events).startswith("[esto no se cierra")


def test_header_without_closing_bracket_ends_at_newline() -> None:
    events, parser = run(["[Hallo | hola · alemán\nEn alemán ", "se dice Hallo."])
    assert parser.reply.display == "Hallo"  # type: ignore[attr-defined]
    assert parser.reply.secondary == "hola · alemán"  # type: ignore[attr-defined]
    assert spoken(events) == "En alemán se dice Hallo."


@pytest.mark.parametrize("raw", ["[Miguel de Cervantes | autor]", "[Miguel de Cervantes | autor"])
def test_header_only_speaks_the_display(raw: str) -> None:
    events, parser = run([raw])
    assert parser.reply.display == "Miguel de Cervantes"  # type: ignore[attr-defined]
    assert spoken(events) == "Miguel de Cervantes, autor"
    assert isinstance(events[-1], SpokenEnd)


def test_empty_header_is_ignored() -> None:
    events, parser = run(["[\nEn alemán se dice Hallo."])
    assert not [e for e in events if isinstance(e, BubbleReady)]
    assert parser.reply.display == "En alemán se dice Hallo."  # type: ignore[attr-defined]
    assert spoken(events) == "En alemán se dice Hallo."


def test_first_sentence() -> None:
    assert first_sentence("Hola. Adiós.") == "Hola."
    assert first_sentence("a" * 100).endswith("…")


def test_repeated_header_is_said_once() -> None:
    # ERRORES.md, 2026-11-11: «10 archivos en Descargas, hay 10 archivos en Descargas».
    _, parser = run(["[10 archivos en Descargas | hay 10 archivos en Descargas]"])
    _, reply = parser.finish()
    assert reply.display == "10 archivos en Descargas" and reply.secondary == ""
    assert reply.spoken == "10 archivos en Descargas"
    _, other = run(["[Hallo | hola · alemán]"])[1].finish()
    assert other.secondary == "hola · alemán"  # lo que no se repite, se queda
