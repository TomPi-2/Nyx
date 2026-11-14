"""Router: ajustes de Windows y de Nyx, red, zoom y los fallos del router de la 6.17 (6.25,
quinta tanda). Escritas antes que las reglas."""

from __future__ import annotations

from typing import Any

import pytest

from nyx.brain.router import Route, route
from nyx.index.service import SystemIndex


def calls(text: str, index: SystemIndex) -> list[tuple[str, dict[str, Any]]] | None:
    result = route(text, index)
    if not isinstance(result, Route):
        return None
    return [(c.name, c.arguments) for c in result.calls]


@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("quiero cambiar el fondo de pantalla", [("open_settings", {"page": "Fondo de pantalla"})]),
        ("tengo que configurar el ratón", [("open_settings", {"page": "Ratón"})]),
        ("¿cómo cambio el idioma?", [("open_settings", {"page": "Idioma y región"})]),
        (
            "no me va el micrófono, llévame a donde se configura",
            [("open_settings", {"page": "Sonido"})],
        ),
        ("llévame a los ajustes del bluetooth", [("open_settings", {"page": "Bluetooth"})]),
        ("quiero cambiarte la voz", [("open_nyx_settings", {"section": "voz"})]),
        # 9.11: su color, su tamaño y los paneles, en el panel junto a Nyx.
        ("quiero cambiar tu color", [("nyx_panel", {"panel": "color"})]),
        ("quiero cambiarte el color", [("nyx_panel", {"panel": "color"})]),
        ("quiero cambiarte el tamaño", [("nyx_panel", {"panel": "tamaño"})]),
        ("cámbiate el color", [("nyx_panel", {"panel": "color"})]),
        ("cambia tu color", [("nyx_panel", {"panel": "color"})]),
        ("cámbiate de tamaño", [("nyx_panel", {"panel": "tamaño"})]),
        ("cambia el color de los paneles", [("nyx_panel", {"panel": "paneles"})]),
        ("quiero cambiar el color de tus paneles", [("nyx_panel", {"panel": "paneles"})]),
        ("quiero cambiar tu aspecto", [("open_nyx_settings", {"section": "apariencia"})]),
        ("quiero cambiarte la letra", [("open_nyx_settings", {"section": "apariencia"})]),
        ("ponte coral", [("nyx_control", {"setting": "color", "value": "coral"})]),
        ("hazte más grande", [("nyx_control", {"setting": "tamaño", "value": "más grande"})]),
        (
            "hazte un poco más pequeño",
            [("nyx_control", {"setting": "tamaño", "value": "más pequeña"})],
        ),
        ("vuélvete enorme", [("nyx_control", {"setting": "tamaño", "value": "más grande"})]),
        ("vivo en Sevilla", [("nyx_control", {"setting": "ciudad", "value": "Sevilla"})]),
        ("quítame internet un rato", [("toggle_wifi", {"enabled": False})]),
        ("desconéctame del wifi", [("toggle_wifi", {"enabled": False})]),
        ("acerca la página, que no veo la letra", [("app_action", {"action": "zoom_in"})]),
        ("haz más grande la letra", [("app_action", {"action": "zoom_in"})]),
        ("aleja un poco la página", [("app_action", {"action": "zoom_out"})]),
        ("cierra el dis cord", [("close_app", {"name": "Discord PTB"})]),
        (
            "busca en esta página la palabra precio",
            [("app_action", {"action": "find"}), ("type_text", {"text": "precio"})],
        ),
        (
            "busca Madrid en la página",
            [("app_action", {"action": "find"}), ("type_text", {"text": "Madrid"})],
        ),
    ],
)
def test_settings_and_more(
    text: str, want: list[tuple[str, dict[str, Any]]], index: SystemIndex
) -> None:
    assert calls(text, index) == want


@pytest.mark.parametrize(
    "text",
    [
        "quiero cambiar de trabajo",
        "tengo que configurar la impresora 3D del taller",
        "vivo en un piso",
        "vivo en casa de mis padres",
        "quítame las ganas",
        "acerca el coche",
        "quiero cambiar la voz del vídeo",  # no es la de Nyx
    ],
)
def test_not_settings(text: str, index: SystemIndex) -> None:
    got = calls(text, index)
    assert got is None or got[0][0] not in {
        "open_settings",
        "open_nyx_settings",
        "nyx_control",
        "toggle_wifi",
        "app_action",
    }, got
