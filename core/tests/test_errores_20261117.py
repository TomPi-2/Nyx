"""Fallos de la prueba del usuario del 2026-11-17 (docs/ERRORES.md), uno por prueba."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from nyx.brain.router import Route, route
from nyx.bus import EventBus
from nyx.events import TextEntered
from nyx.index.service import SystemIndex
from nyx.modes.manager import ModeManager
from nyx.safety.undo import Undo
from nyx.settings.model import Settings
from nyx.tools.base import ToolContext, ToolResult
from nyx.tools.get_weather import tomorrow_only
from nyx.tools.nyx_control import NyxControl, NyxControlParams
from tests.test_pipeline import Harness


@pytest.mark.parametrize(
    ("text", "calls"),
    [
        ("Dezatlo.", [("undo", {})]),
        ("Pégalo en la nota.", [("send_hotkey", {"keys": "ctrl+v", "app": "Bloc de notas"})]),
        (
            "Escribe lo que tengo en el portapapeles en la nota que tengo abierta.",
            [("send_hotkey", {"keys": "ctrl+v", "app": "Bloc de notas"})],
        ),
        (
            "Borra todo lo que hay en la nota abierta.",
            [
                ("send_hotkey", {"keys": "ctrl+a", "app": "Bloc de notas"}),
                ("send_hotkey", {"keys": "backspace", "app": "Bloc de notas"}),
            ],
        ),
        (
            "Abre el bloc de notas y redacta todo lo que yo te diga.",
            [("open_app", {"name": "Bloc de notas"}), ("dictation", {"action": "start"})],
        ),
        (
            "Te voy a dictar y tienes que escribir lo que te diga.",
            [("dictation", {"action": "start"})],
        ),
        ("Empieza el modo dictado.", [("dictation", {"action": "start"})]),
        ("Ahora escribe todo lo que yo te dicté.", [("dictation", {"action": "start"})]),
        ("Cuéntame todo lo que sepas de Tepnyx.", [("nyx_info", {"topic": "tepnyx"})]),
        ("Dime quién te ha creado y qué es.", [("nyx_info", {"topic": "tepnyx"})]),
        (
            "Guarda mi ciudad en la configuración.",
            [("nyx_control", {"setting": "ciudad", "value": "aqui"})],
        ),
        ("Actualiza mi ciudad.", [("nyx_control", {"setting": "ciudad", "value": "aqui"})]),
        ("¿Qué tiempo va a hacer mañana?", [("get_weather", {"day": "tomorrow"})]),
        (
            "Escribe hola en el bloc de notas",
            [("type_text", {"app": "Bloc de notas", "text": "hola"})],
        ),
    ],
)
def test_router(index: SystemIndex, text: str, calls: list[tuple[str, dict[str, Any]]]) -> None:
    routed = route(text, index)
    assert isinstance(routed, Route), text
    assert [(c.name, c.arguments) for c in routed.calls] == calls


def test_files_are_never_cleared_as_text(index: SystemIndex) -> None:
    routed = route("Borra todo lo que hay en descargas", index)
    assert not (isinstance(routed, Route) and routed.rule == "clear_text")


def test_weather_for_tomorrow_only() -> None:
    daily = {
        "weather_code": [3, 61],
        "temperature_2m_max": [23.0, 19.4],
        "temperature_2m_min": [16.0, 12.2],
        "precipitation_probability_max": [3, 80],
    }
    full = ToolResult(ok=True, message="Hoy…", data={"city": "Valencia", "daily": daily})
    got = tomorrow_only(full)
    assert got.message.startswith("Tiempo en Valencia. Mañana:")
    assert "entre 12 y 19 °C" in got.message and "Hoy" not in got.message


async def test_city_here_saves_the_located_city(
    ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    import nyx.tools.nyx_control as module

    saved: list[dict[str, Any]] = []

    async def apply(patch: dict[str, Any]) -> list[str]:
        saved.append(patch)
        return []

    ctx.apply_settings = apply

    async def valencia() -> str | None:
        return "Valencia"

    monkeypatch.setattr(module, "_located_city", valencia)
    got = await NyxControl().run(NyxControlParams(setting="ciudad", value="aqui"), ctx)
    assert got.ok and saved == [{"general": {"city": "Valencia"}}]
    # «La configuración» nunca es una ciudad.
    bad = await NyxControl().run(NyxControlParams(setting="ciudad", value="la configuración"), ctx)
    assert not bad.ok


async def test_automatic_modes_never_open_windows() -> None:
    done: list[str] = []

    async def run(name: str, args: dict[str, Any]) -> ToolResult:
        done.append(name)

        async def back() -> str:
            return ""

        return ToolResult(ok=True, undo=Undo(name, back))

    settings = Settings()
    settings.modes.night_from = "23:00"
    modes = ModeManager(EventBus(), settings, run, clock=lambda: datetime(2026, 11, 17, 23, 29))
    await modes.check_night()
    assert done == ["set_volume"]  # sin abrir Configuración
    await modes.exit()
    await modes.enter("noche")  # pedido: sí abre la luz nocturna
    assert "open_settings" in done


async def test_write_that_text_shows_the_last_answer() -> None:
    h = Harness()
    await h.bus.publish(TextEntered("¿Cómo se dice hola en alemán?"))
    await h.p.wait_idle()
    await h.bus.publish(TextEntered("Escríbeme todo ese texto"))
    await h.p.wait_idle()
    assert h.p._long is not None and "Hallo" in h.p._long.text
    assert len(h.llm.asked) == 1  # no vuelve al modelo
    await h.p.close()
