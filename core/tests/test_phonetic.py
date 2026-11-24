"""Corrector por sonido (Cerebro 2, C1.4): lo que escribe Whisper → el nombre del equipo."""

import pytest

from nyx.index.phonetic import best_by_sound, key, spelled

NAMES = [
    "Spotify", "Fortnite", "Steam", "VALORANT", "Discord", "Epic Games", "Rocket League",
    "League of Legends", "Google Chrome", "Opera GX", "Battle.net", "Visual Studio Code",
    "Bloc de notas", "Calculadora", "WhatsApp", "Twitch", "OBS", "Teams", "Word", "Excel",
    "Minecraft", "Netflix", "Xbox",
]  # fmt: skip
CANDIDATES = [(n, n) for n in NAMES]


@pytest.mark.parametrize(
    ("heard", "name"),
    [
        ("espotifai", "Spotify"),
        ("fortnait", "Fortnite"),
        ("estim", "Steam"),
        ("balorant", "VALORANT"),
        ("dis cord", "Discord"),
        ("discor", "Discord"),
        ("epic gueims", "Epic Games"),
        ("roket ligue", "Rocket League"),
        ("opera ge equis", "Opera GX"),
        ("batel net", "Battle.net"),
        ("o be ese", "OBS"),
        ("tims", "Teams"),
        ("maincraft", "Minecraft"),
        ("netflis", "Netflix"),
        ("equis box", "Xbox"),
    ],
)
def test_sounds_like(heard: str, name: str) -> None:
    found = best_by_sound(heard, CANDIDATES)
    assert found is not None and found.name == name


@pytest.mark.parametrize("heard", ["pon la tele", "dime algo", "la venta", "de", "abre"])
def test_ordinary_words_are_not_names(heard: str) -> None:
    assert best_by_sound(heard, CANDIDATES) is None


def test_same_sound_same_key() -> None:
    assert key("Steam", english=True) == key("estim")
    assert key("vaca") == key("baca")
    assert key("guerra") != key("jerra")  # «gue»: g fuerte, no «je»
    assert key("guerra") == key("guera")
    assert key("gente") == key("jente")


def test_spelled_letters_are_joined() -> None:
    assert spelled(["o", "be", "ese"]) == ["obs"]
    assert spelled(["opera", "ge", "equis"]) == ["opera", "gx"]
    assert spelled(["la", "o"]) == ["la", "o"]  # una sola letra suelta no se junta


def test_two_names_that_sound_alike_are_not_guessed() -> None:
    # «estim» suena igual a «Steam» y a «Stim»: mejor preguntar que elegir al azar.
    assert best_by_sound("estim", [("Steam", "Steam"), ("Stim", "Stim")]) is None
    # Si uno suena exacto y el otro solo parecido, vale el exacto.
    found = best_by_sound("estim", [("Steam", "Steam"), ("Stims", "Stims")])
    assert found is not None and found.name == "Steam"
