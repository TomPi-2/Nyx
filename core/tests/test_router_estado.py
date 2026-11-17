"""Router: preguntas por el estado de las cosas (6.25, tercera tanda). Escritas antes que las
reglas: equipo, alarmas, cronómetro, tiempo y lo que suena."""

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
        # equipo
        ("¿Tengo el portátil enchufado?", "system_info", {"what": "battery"}),
        ("¿está el ordenador cargando?", "system_info", {"what": "battery"}),
        ("¿me queda batería para ver una peli?", "system_info", {"what": "battery"}),
        ("¿qué tal voy de batería?", "system_info", {"what": "battery"}),
        ("¿cuánta memoria me queda libre?", "system_info", {"what": "ram"}),
        ("¿me queda sitio para instalar un juego de 100 gigas?", "system_info", {"what": "disk"}),
        ("¿hay espacio en el disco?", "system_info", {"what": "disk"}),
        ("¿cuánto sitio me queda?", "system_info", {"what": "disk"}),
        ("¿cuál de mis programas está gastando más memoria?", "system_info", {"what": "top"}),
        ("¿qué programa está consumiendo tanta CPU?", "system_info", {"what": "top"}),
        ("¿el ordenador va muy cargado?", "system_info", {"what": "top"}),
        ("¿por qué va tan lento el PC?", "system_info", {"what": "top"}),
        ("el portátil va lentísimo", "system_info", {"what": "top"}),
        # la IP (ERRORES.md, 2026-11-14: el modelo se la inventaba)
        ("¿Cuál es mi IP?", "system_info", {"what": "ip"}),
        ("¿qué IP tengo?", "system_info", {"what": "ip"}),
        ("dime mi dirección IP", "system_info", {"what": "ip"}),
        ("¿qué IP tiene el ordenador?", "system_info", {"what": "ip"}),
        ("mi IP", "system_info", {"what": "ip"}),
        # alarmas
        ("¿a qué hora sonaba la alarma de mañana?", "list_alarms", {}),
        ("¿a qué hora tengo la alarma?", "list_alarms", {}),
        ("¿cuánto falta para que suene el temporizador?", "list_alarms", {}),
        ("¿me puedes decir cuánto falta para mi alarma?", "list_alarms", {}),
        ("¿tengo algo programado para mañana?", "list_alarms", {}),
        # cronómetro
        ("¿cuánto marca el crono?", "stopwatch", {"action": "status"}),
        ("¿cuánto va el cronómetro?", "stopwatch", {"action": "status"}),
        ("cronometra cuánto tardo en hacer esto", "stopwatch", {"action": "start"}),
        ("cronométrame", "stopwatch", {"action": "start"}),
        ("empieza a contar el tiempo", "stopwatch", {"action": "start"}),
        ("ya he terminado, para de contar el tiempo", "stopwatch", {"action": "stop"}),
        ("deja de contar", "stopwatch", {"action": "stop"}),
        # tiempo
        ("¿tengo que coger chaqueta para salir?", "get_weather", {}),
        ("¿hace falta llevar paraguas?", "get_weather", {}),
        ("¿qué tal día va a hacer mañana?", "get_weather", {"day": "tomorrow"}),
        ("¿hará bueno este finde en Valencia?", "get_weather", {"city": "Valencia"}),
        ("¿va a hacer frío mañana?", "get_weather", {"day": "tomorrow"}),
        ("¿está nublado ahora?", "get_weather", {}),
        ("¿está lloviendo en Bilbao?", "get_weather", {"city": "Bilbao"}),
        (
            "¿cuántos grados va a hacer mañana en Barcelona?",
            "get_weather",
            {"city": "Barcelona", "day": "tomorrow"},
        ),
        ("tengo frío, ¿qué temperatura hace fuera?", "get_weather", {}),
        # lo que suena
        ("¿cómo se llama lo que estoy escuchando?", "now_playing", {}),
        ("¿de quién es este tema?", "now_playing", {}),
        ("¿qué grupo es este?", "now_playing", {}),
        ("¿qué artista está sonando?", "now_playing", {}),
        ("¿qué estoy escuchando?", "now_playing", {}),
    ],
)
def test_state_questions(text: str, tool: str, args: dict[str, Any], index: SystemIndex) -> None:
    assert routed(text, index) == (tool, args)


@pytest.mark.parametrize(
    "text",
    [
        "¿qué grupo de música me recomiendas?",
        "tengo que coger el autobús",
        "hace frío en casa",
        "¿hará falta reservar mesa?",
        "el ordenador va muy bien",
        "tengo algo que contarte",
        "¿cuánto falta para Navidad?",
        "para de hablar",
        "deja de contar chistes",
        "¿de quién es este libro?",
        "¿a qué hora abre el súper?",
        "¿me queda bien esta camisa?",
        "¿está nublado mi juicio?",
    ],
)
def test_not_state_questions(text: str, index: SystemIndex) -> None:
    got = routed(text, index)
    assert got is None or got[0] not in {
        "system_info",
        "list_alarms",
        "stopwatch",
        "get_weather",
        "now_playing",
    }, got


@pytest.mark.parametrize(
    ("text", "tool", "args"),
    [
        ("para de cronometrar", "stopwatch", {"action": "stop"}),
        ("¿cuánto le queda al temporizador de la pasta?", "list_alarms", {}),
        ("¿está mi portátil enchufado a la corriente?", "system_info", {"what": "battery"}),
    ],
)
def test_found_by_the_battery(
    text: str, tool: str, args: dict[str, Any], index: SystemIndex
) -> None:
    """Frases nuevas de la batería que fallaron la primera vez (6.25, tanda 3)."""
    assert routed(text, index) == (tool, args)


@pytest.mark.parametrize("text", ["para de hablar", "deja de cantar", "para de reírte"])
def test_stop_doing_something_is_not_pausing_music(text: str, index: SystemIndex) -> None:
    got = routed(text, index)
    assert got is None or got[0] != "media_control", got


@pytest.mark.parametrize(
    ("text", "tool", "args"),
    [
        # Muletillas al principio (ERRORES.md, 2026-11-14).
        ("Vale, ábreme la Netflix.", "open_url", {"target": "Netflix"}),
        ("Venga, pon música", "media_control", {"action": "play", "music": True}),
        ("Bueno, ¿cuánta batería me queda?", "system_info", {"what": "battery"}),
    ],
)
def test_leading_fillers(text: str, tool: str, args: dict[str, Any], index: SystemIndex) -> None:
    assert routed(text, index) == (tool, args)
