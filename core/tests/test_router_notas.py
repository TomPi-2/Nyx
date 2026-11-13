"""Regla de notas (6.28): «apunta en una nota que…» → save_note, con el texto tal cual."""

from __future__ import annotations

import pytest

from nyx.brain.router import Route, route
from nyx.index.service import SystemIndex


@pytest.mark.parametrize(
    ("text", "title", "body"),
    [
        (
            "apunta en una nota que mañana tengo dentista a las cinco",
            "Mañana tengo dentista a las cinco",
            "Mañana tengo dentista a las cinco.",
        ),
        (
            "apúntame que tengo que llamar a Marta",
            "Tengo que llamar a Marta",
            "Tengo que llamar a Marta.",
        ),
        ("toma nota de comprar pilas", "Comprar pilas", "Comprar pilas."),
        (
            "crea una nota que diga la contraseña del wifi está en la nevera",
            "La contraseña del wifi está en…",
            "La contraseña del wifi está en la nevera.",
        ),
        (
            "guarda en una nota la talla de Lucía es la 38",
            "La talla de Lucía es la…",
            "La talla de Lucía es la 38.",
        ),
    ],
)
def test_note_save(index: SystemIndex, text: str, title: str, body: str) -> None:
    routed = route(text, index)
    assert isinstance(routed, Route) and routed.rule == "note_save"
    call = routed.calls[0]
    assert call.name == "save_note"
    assert call.arguments == {"title": title, "text": body}


@pytest.mark.parametrize(
    "text",
    [
        "guarda el documento",
        "escribe en el bloc de notas hola",
        "abre el bloc de notas",
        "recuérdame llamar a Marta",
        "apúntamelo",  # solo con un panel abierto (lo mira el pipeline, no el router)
        "toma nota",
    ],
)
def test_not_a_note(index: SystemIndex, text: str) -> None:
    routed = route(text, index)
    assert not (isinstance(routed, Route) and routed.rule == "note_save")
