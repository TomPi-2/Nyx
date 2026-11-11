"""nyx_info (6.03): Nyx explica cómo funciona en vez de abrir sus ajustes."""

import pytest

from nyx.tools.nyx_info import find, sections


def test_every_section_has_text() -> None:
    known = sections()
    assert {"quien soy", "que se hacer", "modo partida", "ajustes", "lo que nunca hago"} <= set(
        known
    )
    assert all(len(text) > 80 for text in known.values())


@pytest.mark.parametrize(
    ("topic", "starts"),
    [
        ("", "- Abrir y cerrar programas"),
        ("modo partida", "Cuando juegas"),
        ("explícame tu configuración para el modo partida", "Cuando juegas"),
        ("¿qué hay en tus ajustes?", "Se abren desde"),
        ("¿qué cosas no haces nunca?", "- Nada dentro de un juego"),
        ("¿me grabas?", "El audio no se guarda"),
        ("algo que no existe", "- Abrir y cerrar programas"),
    ],
)
def test_find_picks_the_right_section(topic: str, starts: str) -> None:
    assert find(topic).startswith(starts)
