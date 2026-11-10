import pytest

from nyx.wake.custom import WakePhrase, syllables, validate
from nyx.wake.vosk_engine import heard


@pytest.mark.parametrize(
    ("text", "n"), [("Nyx", 1), ("oye", 2), ("Lumen", 2), ("oye Lumen", 4), ("Jarvis", 2)]
)
def test_syllables(text: str, n: int) -> None:
    assert syllables(text) == n


def test_validate() -> None:
    vocab = {"oye", "lumen", "jarvis", "luna", "nix"}.__contains__
    assert validate("Oye Lumen", vocab).ok
    assert not validate("Nix", vocab).ok  # una sílaba
    unknown = validate("Oye Zorblax", vocab)
    assert not unknown.ok and "zorblax" in unknown.problems[0]
    common = validate("Luna", vocab)
    assert common.ok and common.warnings  # se puede, pero saltaría a menudo
    assert not validate("", vocab).ok


def test_nyx_phrase_keeps_current_behaviour() -> None:
    nyx = WakePhrase()
    assert nyx.heard("Nix, ¿qué hora es?") and not nyx.heard("¿qué hora es?")
    assert nyx.without("Nyx, abre Spotify.") == "abre Spotify."


def test_custom_phrase() -> None:
    lumen = WakePhrase.custom("Oye Lumen")
    assert lumen.heard("Oye, Lumen.") and lumen.heard("Oye lumen abre Spotify", first_words=3)
    assert not lumen.heard("Oye, ¿qué hora es?")
    assert lumen.without("Oye, Lumen, abre Spotify.") == "abre Spotify."
    assert lumen.without("abre Spotify") == "abre Spotify"


def test_vosk_heard_multiword() -> None:
    assert heard("oye lumen", "oye lumen") and heard("bueno oye lumen ya", "Oye Lumen")
    assert not heard("oye", "oye lumen")
    assert heard("nix", "nix") and not heard("nixon", "nix")
