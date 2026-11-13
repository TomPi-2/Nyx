"""Router: séptima tanda (6.25), frases que el 7B falló al pasar a 43 herramientas. Escritas
antes que las reglas."""

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
        ("ponte de color rosa", "nyx_control", {"setting": "color", "value": "rosa"}),
        ("cámbiate a color turquesa", "nyx_control", {"setting": "color", "value": "turquesa"}),
        ("ponte azul cielo", "nyx_control", {"setting": "color", "value": "azul cielo"}),
        ("esta canción no me gusta, pásala", "media_control", {"action": "next"}),
        ("este tema no me gusta", "media_control", {"action": "next"}),
        ("llévame a la ventana del Discord", "focus_window", {"name": "Discord PTB"}),
        ("llévame al Spotify", "focus_window", {"name": "Spotify"}),
        ("quítale el sonido al Chrome", "set_volume", {"mute": True, "app": "Google Chrome"}),
        ("quita el sonido del Spotify", "set_volume", {"mute": True, "app": "Spotify"}),
        ("olvida el recordatorio de llamar a mamá", "cancel_alarm", {"which": "llamar a mamá"}),
        ("olvídate de la alarma de las 7", "cancel_alarm", {"which": "7"}),
        ("pon algo para relajarme", "media_control", {"action": "play", "music": True}),
        (
            "ponme algo de música para concentrarme",
            "media_control",
            {"action": "play", "music": True},
        ),
        ("vuelve a poner la música", "media_control", {"action": "play"}),
    ],
)
def test_batch7(text: str, tool: str, args: dict[str, Any], index: SystemIndex) -> None:
    assert first(text, index) == (tool, args)


@pytest.mark.parametrize(
    "text",
    [
        "ponte en mi lugar",
        "ponte las pilas",
        "esta película no me gusta",
        "llévame a casa",
        "llévame a los ajustes del wifi",  # ajustes, no una ventana
        "quítale el polvo al teclado",
        "olvida lo que te he dicho",
        "pon algo de orden en el escritorio",
    ],
)
def test_not_batch7(text: str, index: SystemIndex) -> None:
    got = first(text, index)
    assert got is None or got[0] not in {
        "nyx_control",
        "media_control",
        "focus_window",
        "set_volume",
        "cancel_alarm",
    }, got


@pytest.mark.parametrize(
    ("text", "query"),
    [
        ("busca en internet quién inventó la imprenta", "quién inventó la imprenta"),
        ("búscame en Google recetas de lentejas", "recetas de lentejas"),
        ("busca Napoleón en Wikipedia", "Napoleón"),
    ],
)
def test_web_search_rule(text: str, query: str, index: SystemIndex) -> None:
    assert first(text, index) == ("web_search", {"query": query})


def test_a_question_after_busca_is_not_a_file(index: SystemIndex) -> None:
    """ERRORES.md (2026-11-11): «busca qué aplicaciones ha creado Tepnyx» buscaba archivos."""
    got = first("busca qué aplicaciones ha creado Tepnyx", index)
    assert got is None or got[0] != "find_files"
    assert first("busca el archivo del contrato", index) == (
        "find_files",
        {"query": "contrato"},
    )


@pytest.mark.parametrize(
    "text",
    ["ábreme el último documento que descargué", "abre la foto más reciente", "abre lo que guardé"],
)
def test_open_the_latest_is_for_the_llm(text: str, index: SystemIndex) -> None:
    """ERRORES.md (2026-11-12): no es un nombre («No encuentro…»), son dos pasos (LLM)."""
    assert route(text, index) is None
