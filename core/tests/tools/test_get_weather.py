"""get_weather (6.08): previsión con Open-Meteo, ciudad en Ajustes → General y caché de 15 min."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx

from nyx.game.policy import GameGate
from nyx.settings.live import apply_patch
from nyx.settings.model import GameSettings
from nyx.tools.base import GamePolicy, Risk, ToolContext
from nyx.tools.get_weather import CACHE_TTL_S, GetWeather, GetWeatherParams

GEO_MADRID = {
    "results": [
        {
            "name": "Madrid",
            "latitude": 40.4165,
            "longitude": -3.7026,
            "country": "España",
        }
    ]
}
FORECAST_MADRID = {
    "current": {
        "temperature_2m": 18.4,
        "apparent_temperature": 18.0,
        "weather_code": 0,
        "wind_speed_10m": 12.0,
    },
    "daily": {
        "time": ["2026-11-11", "2026-11-12"],
        "weather_code": [0, 63],
        "temperature_2m_max": [21.8, 16.2],
        "temperature_2m_min": [10.6, 9.8],
        "precipitation_probability_max": [10, 85],
    },
}


def _transport(
    calls: list[httpx.Request],
    *,
    geo: dict[str, Any] = GEO_MADRID,
    forecast: dict[str, Any] = FORECAST_MADRID,
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if "geocoding-api.open-meteo.com" in str(request.url):
            return httpx.Response(200, json=geo)
        return httpx.Response(200, json=forecast)

    return httpx.MockTransport(handler)


def test_metadata() -> None:
    assert GetWeather.risk is Risk.GREEN
    assert GetWeather.game_policy is GamePolicy.ALLOWED
    assert GetWeather.observe is True


async def test_without_city_opens_general_settings(ctx: ToolContext) -> None:
    opened: list[str | None] = []

    async def open_window(section: str | None) -> None:
        opened.append(section)

    ctx = replace(ctx, open_nyx_settings=open_window)
    ctx.settings.general.city = ""
    result = await GetWeather().run(GetWeatherParams(), ctx)
    assert not result.ok
    assert result.message == "Dime tu ciudad en Ajustes → General"
    assert opened == ["general"]

    # En partida se dice, pero no se abre ninguna ventana encima del juego.
    playing = replace(ctx, game=GameGate(GameSettings(), active=True))
    result = await GetWeather().run(GetWeatherParams(), playing)
    assert not result.ok and opened == ["general"]


async def test_fetches_geocoding_and_forecast_with_15_min_cache(ctx: ToolContext) -> None:
    calls: list[httpx.Request] = []
    now = [100.0]
    tool = GetWeather(transport=_transport(calls), clock=lambda: now[0])
    ctx.settings.general.city = "Madrid"

    first = await tool.run(GetWeatherParams(), ctx)
    assert first.ok
    assert first.display == "18 °C · Despejado"
    assert first.secondary == "Madrid · máx. 22° mín. 11° · open-meteo.com"
    assert "Tiempo en Madrid: ahora 18 °C, despejado" in first.message
    assert "Hoy: despejado, entre 11 y 22 °C, probabilidad de lluvia 10 %" in first.message
    assert "Mañana: lluvia, entre 10 y 16 °C, probabilidad de lluvia 85 %" in first.message
    assert len(calls) == 2
    assert calls[0].url.params["name"] == "Madrid"
    assert calls[0].url.params["language"] == "es"
    assert calls[1].url.params["timezone"] == "auto"
    assert "temperature_2m" in calls[1].url.params["current"]
    assert "precipitation_probability_max" in calls[1].url.params["daily"]

    # Dentro de los 15 min: responde desde la caché sin volver a llamar a la red.
    now[0] += CACHE_TTL_S - 1
    cached = await tool.run(GetWeatherParams(), ctx)
    assert cached.ok and len(calls) == 2

    # Pasados los 15 min: actualiza la previsión (las coordenadas ya están en caché).
    now[0] += 2
    refreshed = await tool.run(GetWeatherParams(), ctx)
    assert refreshed.ok and len(calls) == 3


async def test_explicit_city_overrides_settings(ctx: ToolContext) -> None:
    calls: list[httpx.Request] = []
    geo = {"results": [{"name": "Sevilla", "latitude": 37.3886, "longitude": -5.9823}]}
    tool = GetWeather(transport=_transport(calls, geo=geo))
    ctx.settings.general.city = "Madrid"

    result = await tool.run(GetWeatherParams(city="Sevilla"), ctx)
    assert result.ok
    assert calls[0].url.params["name"] == "Sevilla"
    assert "Tiempo en Sevilla" in result.message


async def test_unknown_city_fails_clearly(ctx: ToolContext) -> None:
    calls: list[httpx.Request] = []
    tool = GetWeather(transport=_transport(calls, geo={"results": []}))
    result = await tool.run(GetWeatherParams(city="Atlántida"), ctx)
    assert not result.ok
    assert "No encuentro la ciudad «Atlántida»" in result.message


async def test_network_error_fails_without_crashing(ctx: ToolContext) -> None:
    def failing(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin red", request=request)

    tool = GetWeather(transport=httpx.MockTransport(failing))
    result = await tool.run(GetWeatherParams(city="Madrid"), ctx)
    assert not result.ok
    assert "No tengo conexión" in result.message


def test_general_city_is_editable_without_restart(ctx: ToolContext, tmp_path: Path) -> None:
    restart = apply_patch(
        ctx.settings, {"general": {"city": "Valencia"}}, tmp_path / "settings.json"
    )
    assert restart == []
    assert ctx.settings.general.city == "Valencia"


# --- ciudad automática con la ubicación de Windows (6.24) ---


async def test_without_city_uses_windows_location(ctx: ToolContext) -> None:
    from nyx.winapi.location import Locator

    async def position() -> tuple[float, float]:
        return (39.4699, -0.3763)

    async def name(lat: float, lon: float) -> str:
        return "Valencia"

    calls: list[httpx.Request] = []
    ctx.settings.general.city = ""
    tool = GetWeather(transport=_transport(calls), locator=Locator(position, name))
    result = await tool.run(GetWeatherParams(), ctx)
    assert result.ok and "Tiempo en Valencia" in result.message
    assert result.secondary is not None and result.secondary.startswith("Valencia ·")
    # Sin geocodificar: las coordenadas van directas a la previsión.
    assert len(calls) == 1 and "api.open-meteo.com/v1/forecast" in str(calls[0].url)
    assert "latitude=39.4699" in str(calls[0].url)


async def test_location_without_a_name_still_gives_the_weather(ctx: ToolContext) -> None:
    from nyx.winapi.location import Locator

    async def position() -> tuple[float, float]:
        return (39.4699, -0.3763)

    async def no_name(lat: float, lon: float) -> None:
        return None

    ctx.settings.general.city = ""
    tool = GetWeather(transport=_transport([]), locator=Locator(position, no_name))
    result = await tool.run(GetWeatherParams(), ctx)
    assert result.ok and "Tiempo en tu ubicación" in result.message
    assert result.secondary is not None and result.secondary.startswith("Tu ubicación ·")


async def test_location_off_asks_for_the_city(ctx: ToolContext) -> None:
    from nyx.winapi.location import Locator

    async def off() -> None:
        return None

    opened: list[str] = []

    async def open_settings(section: str) -> None:
        opened.append(section)

    ctx.settings.general.city = ""
    ctx = replace(ctx, open_nyx_settings=open_settings)
    result = await GetWeather(locator=Locator(off)).run(GetWeatherParams(), ctx)
    assert not result.ok and result.message == "Dime tu ciudad en Ajustes → General"
    assert opened == ["general"]


async def test_city_in_settings_wins_over_location(ctx: ToolContext) -> None:
    from nyx.winapi.location import Locator

    asked: list[int] = []

    async def position() -> tuple[float, float]:
        asked.append(1)
        return (0.0, 0.0)

    ctx.settings.general.city = "Madrid"
    tool = GetWeather(transport=_transport([]), locator=Locator(position))
    assert (await tool.run(GetWeatherParams(), ctx)).ok
    assert asked == []
