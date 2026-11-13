"""Respuestas habladas con variantes según el tono (6.26)."""

from __future__ import annotations

import itertools
import random
import re
from typing import Any

import pytest

from nyx.brain.answers import ANSWERS, THANKS_REPLIES, Answers, answer_key, is_thanks
from nyx.tools.base import ToolResult

TONES = ("cercano", "neutro", "divertido")

# Datos de ejemplo para cada respuesta (varios casos cuando la frase cambia con ellos).
SAMPLES: dict[str, list[dict[str, Any]]] = {
    "battery": [
        {"percent": 76, "plugged": True, "remaining_min": 0},
        {"percent": 23, "plugged": False, "remaining_min": 125},
        {"percent": 50, "plugged": False, "remaining_min": 40},
    ],
    "no_battery": [{}],
    "cpu": [{"percent": 12}, {"percent": 91}],
    "ram": [
        {"used_gb": 9, "total_gb": 32, "percent": 28},
        {"used_gb": 29, "total_gb": 32, "percent": 90},
    ],
    "disk": [
        {"unit": "C:", "free_gb": 120, "total_gb": 931},
        {"unit": "D:", "free_gb": 8, "total_gb": 465},
    ],
    "top_same": [{"cpu_name": "Chrome", "cpu_pct": 34, "ram_name": "Chrome", "ram": "2,1 GB"}],
    "top_split": [
        {"cpu_name": "Rocket League", "cpu_pct": 41, "ram_name": "Chrome", "ram": "3 GB"}
    ],
    "playing": [
        {"title": "Bohemian Rhapsody", "artist": "Queen", "app": "Spotify"},
        {"title": "Lo-fi beats", "artist": "", "app": "YouTube"},
    ],
    "paused": [{"title": "Bohemian Rhapsody", "artist": "Queen", "app": "Spotify"}],
    "silence": [{}],
    "stopwatch_running": [{"elapsed_s": 95}, {"elapsed_s": 3600}],
    "stopwatch_stopped": [{"elapsed_s": 754}],
    "stopwatch_stop": [{"elapsed_s": 42}],
    "stopwatch_none": [{}],
    "no_alarms": [{}],
}

# Palabras que solo existen con tilde: si aparecen sin ella, la frase está mal escrita.
NEED_ACCENT = (
    "bateria",
    "cancion",
    "cronometro",
    "musica",
    "energia",
    "reproduccion",
    "gloton",
    "aqui",
    "tambien",
    "ningun",
    "dia",
)


def all_texts() -> list[tuple[str, str, str]]:
    out = []
    for key, by_tone in ANSWERS.items():
        for tone in TONES:
            for i, variant in enumerate(by_tone[tone]):  # type: ignore[index]
                for data in SAMPLES[key]:
                    out.append((f"{key}/{tone}/{i}", variant(data), key))
    return out


def test_every_answer_has_samples_and_every_tone() -> None:
    assert set(SAMPLES) == set(ANSWERS)
    for key, by_tone in ANSWERS.items():
        assert set(by_tone) == set(TONES), key
        assert all(len(v) >= 1 for v in by_tone.values()), key
        assert len(by_tone["cercano"]) >= 2 and len(by_tone["divertido"]) >= 2, key


@pytest.mark.parametrize(("where", "text", "key"), all_texts())
def test_well_written(where: str, text: str, key: str) -> None:
    first = text[0]
    assert first.isupper() or first.isdigit() or first in "«¿¡", where
    assert text.endswith((".", "?", "!")), where
    assert "  " not in text and " ." not in text and " ," not in text, where
    assert not re.search(r"\{|\}|None|\.\.(?!\.)", text), where
    words = re.findall(r"[a-záéíóúñü]+", text.lower())
    for bare in NEED_ACCENT:
        assert bare not in words, f"{where}: «{bare}» sin tilde en {text!r}"


def test_no_repeats_and_tone_respected() -> None:
    answers = Answers("divertido", random.Random(1))
    result = ToolResult(ok=True, message="m", speak=True, data={"playing": False, "title": ""})
    said = [answers.say("now_playing", {}, result) for _ in range(8)]
    assert all(s for s in said)
    assert all(a != b for a, b in itertools.pairwise(said))
    divertido = {v({}) for v in ANSWERS["silence"]["divertido"]}
    assert set(said) <= divertido


def test_falls_back_to_the_tool_message() -> None:
    answers = Answers()
    # Varios discos: no hay variantes, se dice el mensaje de la herramienta.
    two = ToolResult(
        ok=True,
        message="m",
        data={"what": "disk", "disks": [{"unit": "C:"}, {"unit": "D:"}]},
    )
    assert answers.say("system_info", {"what": "disk"}, two) is None
    # Faltan datos: mejor el mensaje que una frase rota.
    broken = ToolResult(ok=True, message="m", data={"what": "cpu"})
    assert answers.say("system_info", {"what": "cpu"}, broken) is None
    assert answer_key("get_weather", {}, ToolResult(ok=True, message="m")) is None


def test_keys_from_real_results() -> None:
    def key(tool: str, args: dict[str, Any], data: dict[str, Any]) -> str | None:
        found = answer_key(tool, args, ToolResult(ok=True, message="m", data=data))
        return None if found is None else found[0]

    assert key("system_info", {}, {"what": "battery", "has_battery": False}) == "no_battery"
    assert key("stopwatch", {"action": "status"}, {"running": False, "elapsed_s": 0}) == (
        "stopwatch_none"
    )
    assert key("stopwatch", {"action": "status"}, {"running": False, "elapsed_s": 9}) == (
        "stopwatch_stopped"
    )
    assert key("stopwatch", {"action": "start"}, {"running": True}) is None  # en silencio
    assert key("list_alarms", {}, {"ids": [1]}) is None  # la lista la dice la herramienta
    assert key("list_alarms", {}, {}) == "no_alarms"


# --- agradecimientos (6.27) ---


@pytest.mark.parametrize(
    "text",
    [
        "gracias",
        "Gracias, Nyx",
        "¡Muchas gracias!",
        "mil gracias de verdad",
        "vale, gracias",
        "perfecto, muchas gracias Nyx",
        "genial gracias por la ayuda",
        "Nyx, gracias",
        "te lo agradezco",
        "muy amable",
    ],
)
def test_thanks(text: str) -> None:
    assert is_thanks(text)


@pytest.mark.parametrize(
    "text",
    [
        "no, gracias",
        "sí, gracias",
        "gracias, ahora pon música",
        "pon música, gracias",
        "dale las gracias a Marta",
        "¿cómo se dice gracias en alemán?",
        "escribe gracias en el chat",
        "vale",
        "perfecto",
    ],
)
def test_not_thanks(text: str) -> None:
    assert not is_thanks(text)


@pytest.mark.parametrize("tone", TONES)
def test_thanks_replies_vary_and_never_repeat_the_last(tone: str) -> None:
    answers = Answers(tone, random.Random(3))  # type: ignore[arg-type]
    said = [answers.thanks("gracias") for _ in range(12)]
    assert all(s and (s[0].isupper() or s[0] == "¡") for s in said)
    assert all(a != b for a, b in itertools.pairwise(said))
    assert len(set(said)) == len(THANKS_REPLIES[tone])  # type: ignore[index]
    assert answers.thanks("pon música") is None
