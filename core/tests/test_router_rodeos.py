"""Router: órdenes con rodeos (6.25, sexta tanda). Escritas antes que las reglas: alarmas y
temporizadores contados de otra forma, archivos, brillo, volver a una app, seguir con la música,
abrir con explicación detrás y ajustes de Nyx."""

from __future__ import annotations

from typing import Any

import pytest

from nyx.brain.router import Route, route
from nyx.index.service import SystemIndex


def first(text: str, index: SystemIndex) -> tuple[str, dict[str, Any]] | None:
    result = route(text, index)
    if not isinstance(result, Route) or len(result.calls) != 1:
        return None
    return result.calls[0].name, result.calls[0].arguments


@pytest.mark.parametrize(
    ("text", "tool", "args"),
    [
        # alarmas y temporizadores
        (
            "mañana tengo que levantarme a las seis y media",
            "set_alarm",
            {"time": "06:30", "day": "tomorrow"},
        ),
        ("tengo que levantarme a las 7", "set_alarm", {"time": "07:00"}),
        (
            "quiero que me despiertes a las 9 los fines de semana",
            "set_alarm",
            {"time": "09:00", "repeat": "weekends"},
        ),
        ("la pasta tarda 12 minutos, avísame cuando esté", "set_timer", {"minutes": 12}),
        ("el pan tarda media hora, avísame", "set_timer", {"minutes": 30}),
        ("en un cuarto de hora tengo que salir, avísame", "set_timer", {"minutes": 15}),
        ("cuenta tres minutos para el té", "set_timer", {"minutes": 3}),
        # archivos
        ("¿tengo algo en el escritorio?", "list_files", {"folder": "escritorio"}),
        ("dime qué he descargado últimamente", "list_files", {"folder": "Descargas", "newest": 5}),
        ("¿qué me he descargado hoy?", "list_files", {"folder": "Descargas", "newest": 5}),
        # brillo
        ("me deslumbra la pantalla", "set_brightness", {"change": -20}),
        ("la pantalla está demasiado brillante", "set_brightness", {"change": -20}),
        ("no veo nada, la pantalla está muy oscura", "set_brightness", {"change": 20}),
        # volver a una app, música
        ("vuelve al Visual Studio Code", "focus_window", {"name": "Visual Studio Code"}),
        ("vuelve a Spotify", "focus_window", {"name": "Spotify"}),
        ("sigue con la música", "media_control", {"action": "play"}),
        ("vuelve a la página anterior", "app_action", {"action": "back"}),
        # abrir con explicación detrás
        (
            "arranca el Discord que voy a hablar con los colegas",
            "open_app",
            {"name": "Discord PTB"},
        ),
        ("abre Spotify para escuchar algo", "open_app", {"name": "Spotify"}),
        (
            "abre lo del bluetooth para emparejar unos cascos",
            "open_settings",
            {"page": "Bluetooth"},
        ),
        # Nyx
        ("¿dónde veo los atajos que has aprendido?", "open_nyx_settings", {"section": "cerebro"}),
        (
            "cuando te escriba no me contestes hablando",
            "nyx_control",
            {"setting": "voz al escribir", "value": "no"},
        ),
        (
            "no te actives tan fácilmente",
            "nyx_control",
            {"setting": "sensibilidad", "value": "menos"},
        ),
    ],
)
def test_said_another_way(text: str, tool: str, args: dict[str, Any], index: SystemIndex) -> None:
    assert first(text, index) == (tool, args)


@pytest.mark.parametrize(
    "text",
    [
        "mañana tengo que levantarme pronto",  # sin hora: el LLM pregunta
        "la pasta tarda mucho",
        "cuenta un chiste",
        "cuéntame algo",
        "¿tengo algo que hacer?",
        "vuelve a intentarlo",
        "sigue con lo tuyo",
        "abre la puerta que llaman",
        "la pantalla está rota",
        "me deslumbra el sol",
    ],
)
def test_not_these_shortcuts(text: str, index: SystemIndex) -> None:
    got = first(text, index)
    assert got is None or got[0] not in {
        "set_alarm",
        "set_timer",
        "list_files",
        "set_brightness",
        "focus_window",
        "open_app",
        "open_settings",
        "nyx_control",
    }, got
