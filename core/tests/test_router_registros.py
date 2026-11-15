"""Frases reales de los registros del usuario (hasta el 2026-11-15) que obligaban a repetir.

Cada una, tal como la transcribió Whisper (ya sin «Nyx»). Antes iban mal: «salta la canción»
en partida se negaba como si fuera saltar en el juego, «guarda esta canción en favoritos» o
«cierra tus ajustes» llegaban al modelo, que decía «vale» sin hacer nada, y «reiníciate»
quería reiniciar el ordenador.
"""

from __future__ import annotations

from typing import Any

import pytest

from nyx.brain.router import Route, refusal, route
from nyx.index.service import SystemIndex


@pytest.mark.parametrize(
    ("text", "tool", "args"),
    [
        ("Salta la canción.", "media_control", {"action": "next"}),
        ("Salta la canción en Spotify.", "media_control", {"action": "next"}),
        ("Salta la siguiente canción.", "media_control", {"action": "next"}),
        ("Pasa la canción.", "media_control", {"action": "next"}),
        ("Cambia a la siguiente canción.", "media_control", {"action": "next"}),
        ("Guarda esta canción en favoritos.", "app_action", {"app": "Spotify", "action": "like"}),
        ('Guarda esta canción en "me gusta".', "app_action", {"app": "Spotify", "action": "like"}),
        ("Cierra tus ajustes.", "close_nyx_settings", {}),
        ("Cerra tus ajustes.", "close_nyx_settings", {}),
        ("Ahora cierra tus ajustes.", "close_nyx_settings", {}),
        ("Reiníciate.", "nyx_restart", {}),
        ("Reiníciate tú.", "nyx_restart", {}),
        ("Reinicia tu núcleo.", "nyx_restart", {}),
    ],
)
def test_real_phrases(index: SystemIndex, text: str, tool: str, args: dict[str, Any]) -> None:
    routed = route(text, index)
    assert isinstance(routed, Route), text
    (call,) = routed.calls
    assert call.name == tool and call.arguments == args


@pytest.mark.parametrize(
    "text",
    [
        "Salta la canción.",
        "Salta la siguiente canción en Spotify.",
        "salta el anuncio de YouTube",
        "apunta pan en la lista de la compra",
    ],
)
def test_music_and_lists_are_not_the_game(index: SystemIndex, text: str) -> None:
    assert refusal(text, index, playing=True) is None


@pytest.mark.parametrize(
    "text", ["salta", "salta más alto", "acelera", "dispara al de la izquierda"]
)
def test_the_game_still_is(index: SystemIndex, text: str) -> None:
    assert refusal(text, index, playing=True) is not None


def test_restarting_the_pc_is_still_the_pc(index: SystemIndex) -> None:
    routed = route("reinicia el ordenador", index)
    assert isinstance(routed, Route) and routed.calls[0].name == "system_power"
