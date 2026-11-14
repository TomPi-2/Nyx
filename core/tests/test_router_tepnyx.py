"""Router: Tepnyx (2026-11-14). Quién ha creado a Nyx, qué son las apps de Tepnyx, abrir sus
páginas y llevar a las pantallas de Nyx."""

from __future__ import annotations

from typing import Any

import pytest

from nyx.brain.router import Route, route
from nyx.index.service import SystemIndex
from nyx.tools.nyx_info import NyxInfo, NyxInfoParams


def routed(text: str, index: SystemIndex) -> tuple[str, dict[str, Any]] | None:
    result = route(text, index)
    if not isinstance(result, Route) or len(result.calls) != 1:
        return None
    return result.calls[0].name, result.calls[0].arguments


CREATOR = ("nyx_info", {"topic": "quien me ha creado"})


@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("¿Quién te ha creado?", CREATOR),
        ("¿quién es tu creador?", CREATOR),
        ("¿Quién te hizo?", CREATOR),
        ("¿Qué empresa te ha hecho?", CREATOR),
        ("¿De qué empresa eres?", CREATOR),
        ("¿Quién te ha programado?", CREATOR),
        ("¿Qué es Tepnyx?", ("nyx_info", {"topic": "tepnyx"})),
        ("¿Qué es Decider Bot?", ("nyx_info", {"topic": "decider bot"})),
        ("háblame de Sorty", ("nyx_info", {"topic": "sorty"})),
        ("¿qué apps tiene Tepnyx?", ("nyx_info", {"topic": "tepnyx"})),
        ("¿para qué sirve Decider Live?", ("nyx_info", {"topic": "decider live"})),
        # Las páginas de tepnyx.com
        ("abre la web de Tepnyx", ("open_url", {"target": "Tepnyx"})),
        ("abre Decider Bot", ("open_url", {"target": "Decider Bot"})),
        ("abre la ruleta de sí o no", ("open_url", {"target": "Ruleta de sí o no"})),
        ("abre Tepnyx Premium", ("open_url", {"target": "Tepnyx Premium"})),
        ("abre el contacto de Tepnyx", ("open_url", {"target": "Contacto de Tepnyx"})),
        ("abre Podio", ("open_url", {"target": "Podio"})),
        # Las pantallas de Nyx
        ("¿Dónde cambio tu voz?", ("open_nyx_settings", {"section": "voz"})),
        (
            "¿dónde se cambia la palabra de activación de Nyx?",
            ("open_nyx_settings", {"section": "activacion"}),
        ),
        ("¿cómo cambio tu color?", ("open_nyx_settings", {"section": "apariencia"})),
        ("¿dónde veo tus atajos aprendidos?", ("open_nyx_settings", {"section": "cerebro"})),
    ],
)
def test_tepnyx(text: str, want: tuple[str, dict[str, Any]], index: SystemIndex) -> None:
    assert routed(text, index) == want


@pytest.mark.parametrize(
    "text",
    [
        "¿Dónde cambio el micrófono?",  # puede ser el de Windows: lo decide el modelo
        "¿Qué es un podio?",
    ],
)
def test_not_tepnyx(text: str, index: SystemIndex) -> None:
    result = routed(text, index)
    assert result is None or result[0] not in ("nyx_info", "open_nyx_settings")


async def test_the_creator_is_said_as_is(ctx: Any) -> None:
    result = await NyxInfo().run(NyxInfoParams(topic="quien me ha creado"), ctx)
    assert result.ok and result.speak
    assert "Tepnyx" in result.message
