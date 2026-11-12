import pytest

from nyx.stt.normalize import (
    has_wake_word,
    is_hallucination,
    normalize,
    normalize_times,
    strip_wake_word,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Nix, como se dice hola en alemán.", "Como se dice hola en alemán."),
        ("NYAX, abre Visual Studio Code.", "Abre Visual Studio Code."),
        ("nyx abre Valorant", "Abre Valorant"),
        ("Oye Nyx, ¿qué hora es?", "¿Qué hora es?"),
        ("¿Nyx? ¿Qué está sonando?", "¿Qué está sonando?"),
        ("¡Nyx! Abre Spotify.", "Abre Spotify."),
        ("¿Mix? ¿Cuánta RAM uso?", "¿Cuánta RAM uso?"),
        ("Mix de canciones", "Mix de canciones"),
        ("¿Qué día es hoy?", "¿Qué día es hoy?"),
        ("Nixon fue presidente", "Nixon fue presidente"),  # no es la palabra de activación
    ],
)
def test_normalize_strips_wake_word(raw: str, expected: str) -> None:
    assert normalize(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Pon una alarma a las 10 y 50.", "Pon una alarma a las 10:50."),
        ("pon una alarma a las diez cincuenta", "pon una alarma a las 10:50"),
        ("avísame a las diez y cincuenta y cinco", "avísame a las 10:55"),
        ("a la una y media", "a la 1:30"),
        ("a las once menos cuarto", "a las 10:45"),
        ("a las siete y cuarto", "a las 7:15"),
        ("a las dieciséis y veinte", "a las 16:20"),
        ("a las 8 05", "a las 8:05"),
        ("mueve los últimos cinco archivos", "mueve los últimos cinco archivos"),
        ("a las tres", "a las tres"),
        ("a las diez cuarto", "a las diez cuarto"),
    ],
)
def test_times(raw: str, expected: str) -> None:
    assert normalize_times(raw) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "Subtítulos realizados por la comunidad de Amara.org",
        "¡Gracias por ver el vídeo!",
        "[Música]",
        "Nyx.",
    ],
)
def test_hallucinations_and_empty(text: str) -> None:
    assert normalize(text) == ""


def test_is_hallucination_keeps_real_requests() -> None:
    assert not is_hallucination("Gracias, ahora abre Spotify")


def test_strip_wake_word_only_at_start() -> None:
    assert strip_wake_word("abre nix") == "abre nix"


@pytest.mark.parametrize(
    ("text", "anywhere", "first3"),
    [
        ("Nix, ¿qué hora es?", True, True),
        ("NYAX, abre Visual Studio Code.", True, True),
        ("Oye Nyx, abre Spotify", True, True),
        ("eso no existe, nix", True, False),
        ("No existe.", False, False),
        ("En el de mi pein, en el de mi pride", False, False),
        ("¿Mix? ¿Cuánta RAM uso?", False, False),
        ("Nixon fue presidente", False, False),
    ],
)
def test_has_wake_word(text: str, anywhere: bool, first3: bool) -> None:
    assert has_wake_word(text) is anywhere
    assert has_wake_word(text, first_words=3) is first3
