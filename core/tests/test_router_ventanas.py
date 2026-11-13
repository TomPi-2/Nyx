"""Router: ventanas dichas de otra forma (6.25, segunda tanda). Escritas antes que las reglas."""

from __future__ import annotations

import pytest

from nyx.brain.router import Route, route
from nyx.index.service import SystemIndex


def layout(text: str, index: SystemIndex) -> tuple[str, str | None] | None:
    routed = route(text, index)
    if not isinstance(routed, Route) or len(routed.calls) != 1:
        return None
    call = routed.calls[0]
    if call.name != "window_layout":
        return None
    name = call.arguments.get("name")
    return str(call.arguments["action"]), None if name is None else str(name)


@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("pon el Chrome en grande", ("maximize", "chrome")),
        ("pon la ventana en grande", ("maximize", None)),
        ("deja Spotify a pantalla grande", ("maximize", "spotify")),
        ("haz más grande esta ventana", ("maximize", None)),
        ("hazme el Discord más grande", ("maximize", "discord")),
        ("minimisa el crome", ("minimize", "Google Chrome")),  # Whisper: «crome»
        ("maximisa Spotify", ("maximize", "spotify")),
        ("quita de en medio esta ventana", ("minimize", None)),
        ("quítame el Discord de en medio", ("minimize", "discord")),
        ("aparta esta ventana", ("minimize", None)),
        ("manda Spotify abajo", ("minimize", "spotify")),
        ("vuelve a poner el Chrome como estaba", ("restore", "chrome")),
    ],
)
def test_window_phrases(text: str, want: tuple[str, str | None], index: SystemIndex) -> None:
    assert layout(text, index) == want


@pytest.mark.parametrize(
    "text",
    [
        "pon la música más alta",
        "haz más grande la letra",  # zoom, no la ventana
        "pon el volumen en grande",
        "quita de en medio los archivos del escritorio",
        "aparta un rato para mí",
        "pon el Chrome en inglés",
    ],
)
def test_not_window_layout(text: str, index: SystemIndex) -> None:
    assert layout(text, index) is None
