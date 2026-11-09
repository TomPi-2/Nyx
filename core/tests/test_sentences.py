from nyx.tts.sentences import SentenceSplitter


def feed_all(text: str, size: int = 1) -> list[str]:
    splitter = SentenceSplitter()
    out: list[str] = []
    for i in range(0, len(text), size):
        out += splitter.feed(text[i : i + size])
    if rest := splitter.flush():
        out.append(rest)
    return out


def test_splits_sentences_as_they_arrive() -> None:
    splitter = SentenceSplitter()
    assert splitter.feed("Hola. Qué") == ["Hola."]
    assert splitter.feed(" tal? Bien") == ["Qué tal?"]
    assert splitter.flush() == "Bien"


def test_does_not_split_decimals_or_abbreviations() -> None:
    assert feed_all("Mide 3.5 metros, aprox. dos pasos. Fin.") == [
        "Mide 3.5 metros, aprox. dos pasos.",
        "Fin.",
    ]


def test_long_clause_splits_at_comma_short_does_not() -> None:
    text = "Hoy hace un día estupendo en toda la península, con sol. Sí, claro."
    assert feed_all(text, size=4) == [
        "Hoy hace un día estupendo en toda la península,",
        "con sol.",
        "Sí, claro.",
    ]


def test_skips_pieces_without_words() -> None:
    assert feed_all("... ¡Hola!") == ["¡Hola!"]
    assert SentenceSplitter().flush() is None
