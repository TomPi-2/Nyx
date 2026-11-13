"""Router: sonido y música dichos de otra forma (6.25, cuarta tanda). Escritas antes que las
reglas."""

from __future__ import annotations

from typing import Any

import pytest

from nyx.brain.router import Route, route
from nyx.index.service import SystemIndex


def routed(text: str, index: SystemIndex) -> tuple[str, dict[str, Any]] | None:
    result = route(text, index)
    if not isinstance(result, Route) or len(result.calls) != 1:
        return None
    return result.calls[0].name, result.calls[0].arguments


@pytest.mark.parametrize(
    ("text", "tool", "args"),
    [
        ("sube el bolumen", "set_volume", {"change": 10}),
        ("baja el bolumen", "set_volume", {"change": -10}),
        ("baja el volumen de Discord a un 30", "set_volume", {"level": 30, "app": "Discord PTB"}),
        ("pon el volumen a un 40", "set_volume", {"level": 40}),
        ("el Discord se oye demasiado fuerte", "set_volume", {"change": -10, "app": "Discord PTB"}),
        ("Discord está muy alto", "set_volume", {"change": -10, "app": "Discord PTB"}),
        ("el Valorant se oye muy bajo", "set_volume", {"change": 10, "app": "VALORANT"}),
        ("no oigo nada, sube eso", "set_volume", {"change": 10}),
        ("no se oye nada", "set_volume", {"change": 10}),
        ("vuelve a poner la canción de antes", "media_control", {"action": "previous"}),
        ("pon otra vez la de antes", "media_control", {"action": "previous"}),
        ("salta este vídeo de YouTube", "media_control", {"action": "next"}),
        ("sáltate esta canción", "media_control", {"action": "next"}),
        ("pon la música en aleatorio", "app_action", {"app": "Spotify", "action": "shuffle"}),
        (
            "pon las canciones en modo aleatorio",
            "app_action",
            {"app": "Spotify", "action": "shuffle"},
        ),
    ],
)
def test_sound_phrases(text: str, tool: str, args: dict[str, Any], index: SystemIndex) -> None:
    assert routed(text, index) == (tool, args)


@pytest.mark.parametrize(
    "text",
    [
        "no oigo nada de lo que dices",
        "el Discord está muy bien",
        "baja la persiana",
        "se oye un ruido raro",
        "salta la comba",
        "la de antes era mejor",
    ],
)
def test_not_sound_shortcuts(text: str, index: SystemIndex) -> None:
    got = routed(text, index)
    assert got is None, got
