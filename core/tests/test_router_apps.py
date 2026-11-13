"""Router: abrir apps por lo que se necesita (6.25, primera tanda).

Escritas antes que las reglas. Solo se abre algo si el nombre coincide exacto con una app o
un juego del equipo; si no, la frase va al LLM (mejor sin regla que con una que se equivoca).
"""

from __future__ import annotations

import pytest

from nyx.brain.router import Route, route
from nyx.index.service import SystemIndex


def opened(text: str, index: SystemIndex) -> str | None:
    routed = route(text, index)
    if not isinstance(routed, Route) or len(routed.calls) != 1:
        return None
    call = routed.calls[0]
    return str(call.arguments["name"]) if call.name == "open_app" else None


@pytest.mark.parametrize(
    ("text", "app"),
    [
        ("necesito la calculadora", "Calculadora"),
        ("me hace falta la calculadora", "Calculadora"),
        ("Necesito Spotify, por favor.", "Spotify"),
        ("quiero usar el bloc de notas", "Bloc de notas"),
        ("me hace falta el Visual Studio Code para programar", "Visual Studio Code"),
        ("necesito hacer unas cuentas", "Calculadora"),
        ("tengo que calcular una cosa", "Calculadora"),
        ("quiero escuchar música con Spotify", "Spotify"),
        ("vamos a jugar al Valorant", "VALORANT"),
        ("me apetece echar una partida al lol", "League of Legends"),
        ("quiero jugar al Rocket League", "Rocket League®"),
        ("vamos a echar unas partidas al Valorant", "VALORANT"),
    ],
)
def test_opens_what_is_needed(text: str, app: str, index: SystemIndex) -> None:
    assert opened(text, index) == app


@pytest.mark.parametrize(
    "text",
    [
        "necesito ayuda",
        "necesito un descanso",
        "quiero música",
        "necesito tiempo para pensar",
        "necesito que me ayudes con los deberes",
        "quiero jugar a algo",
        "vamos a jugar",
        "tengo que hacer la cena",
        "me hace falta dormir",
        "necesito notas",  # sin artículo: nombre genérico, no la app
        "quiero hacer una presentación",  # no hay PowerPoint ni Impress instalados
        "necesito la impresora",  # no es una app del equipo
        "quiero jugar al ajedrez",  # no está instalado
        "necesito saber qué hora es",
    ],
)
def test_does_not_guess(text: str, index: SystemIndex) -> None:
    assert opened(text, index) is None
