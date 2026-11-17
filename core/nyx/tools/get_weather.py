"""get_weather: previsión del tiempo con Open-Meteo (verde, observe, permitida en partida, 6.08).

Geocodificación (`https://geocoding-api.open-meteo.com/v1/search`) y previsión actual + diaria
(`https://api.open-meteo.com/v1/forecast` con `current`, `daily` y `timezone=auto`). Si no se
indica ciudad en la petición, usa `settings.general.city`; si tampoco está configurada, la
ubicación de Windows (6.24, `winapi/location.py`), y si no hay, abre Ajustes → General y pide
al usuario que la escriba. Caché en memoria de 15 min (SPEC §14).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any, Literal

import httpx
from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from nyx.index.aliases import normalize
from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult
from nyx.winapi.location import Locator

log = logging.getLogger(__name__)

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
CACHE_TTL_S = 15 * 60.0
HTTP_TIMEOUT_S = 5.0

WMO_CODES: dict[int, str] = {
    0: "despejado",
    1: "casi despejado",
    2: "parcialmente nublado",
    3: "nublado",
    45: "niebla",
    48: "niebla helada",
    51: "llovizna débil",
    53: "llovizna",
    55: "llovizna intensa",
    56: "llovizna helada",
    57: "llovizna helada intensa",
    61: "lluvia débil",
    63: "lluvia",
    65: "lluvia fuerte",
    66: "lluvia helada",
    67: "lluvia helada fuerte",
    71: "nieve débil",
    73: "nieve",
    75: "nieve fuerte",
    77: "granizo menudo",
    80: "chubascos débiles",
    81: "chubascos",
    82: "chubascos fuertes",
    85: "chubascos de nieve",
    86: "chubascos de nieve fuertes",
    95: "tormenta",
    96: "tormenta con granizo",
    99: "tormenta fuerte con granizo",
}


def describe_code(code: Any) -> str:
    try:
        return WMO_CODES.get(int(code), "variable")
    except TypeError, ValueError:
        return "variable"


def _day_summary(label: str, daily: dict[str, Any], index: int) -> str:
    codes = daily.get("weather_code") or []
    highs = daily.get("temperature_2m_max") or []
    lows = daily.get("temperature_2m_min") or []
    rains = daily.get("precipitation_probability_max") or []
    parts: list[str] = []
    if index < len(codes) and codes[index] is not None:
        parts.append(describe_code(codes[index]))
    if (
        index < len(lows)
        and index < len(highs)
        and lows[index] is not None
        and highs[index] is not None
    ):
        lo, hi = round(float(lows[index])), round(float(highs[index]))
        parts.append(f"entre {lo} y {hi} °C")
    if index < len(rains) and rains[index] is not None:
        rain = round(float(rains[index]))
        parts.append(f"probabilidad de lluvia {rain} %")
    return f"{label}: {', '.join(parts)}" if parts else ""


def format_weather(place: str, data: dict[str, Any]) -> ToolResult:
    current = data.get("current") or {}
    daily = data.get("daily") or {}
    temp = current.get("temperature_2m")
    feels = current.get("apparent_temperature")
    wind = current.get("wind_speed_10m")
    sky = describe_code(current.get("weather_code"))

    now_temp = f"{round(float(temp))} °C" if isinstance(temp, int | float) else ""
    feels_part = (
        f" (sensación de {round(float(feels))} °C)"
        if isinstance(feels, int | float)
        and isinstance(temp, int | float)
        and abs(round(float(feels)) - round(float(temp))) >= 2
        else ""
    )
    wind_part = (
        f", viento de {round(float(wind))} km/h"
        if isinstance(wind, int | float) and round(float(wind)) >= 20
        else ""
    )
    now_bits = [b for b in (now_temp + feels_part, sky) if b]
    sentences = [f"Tiempo en {place}: ahora {', '.join(now_bits)}{wind_part}".strip()]
    for idx, label in ((0, "Hoy"), (1, "Mañana")):
        if day := _day_summary(label, daily, idx):
            sentences.append(day)
    message = ". ".join(sentences) + "."

    shown = place[:1].upper() + place[1:]  # «tu ubicación» → «Tu ubicación» en el panel
    display = f"{now_temp} · {sky.capitalize()}" if now_temp else f"{shown} · {sky.capitalize()}"
    highs = daily.get("temperature_2m_max") or []
    lows = daily.get("temperature_2m_min") or []
    if highs and lows and highs[0] is not None and lows[0] is not None:
        secondary = (
            f"{shown} · máx. {round(float(highs[0]))}° mín. {round(float(lows[0]))}°"
            " · open-meteo.com"
        )
    else:
        secondary = f"{shown} · open-meteo.com"

    return ToolResult(
        ok=True,
        message=message,
        display=display,
        secondary=secondary,
        data={"city": place, "source": "open-meteo.com", "current": current, "daily": daily},
    )


class GetWeatherParams(Params):
    city: str = Field(default="", max_length=100, description="Ciudad (vacío = la de Ajustes)")
    # Solo lo pone el router («¿qué tiempo hará mañana?»): fuera del esquema del modelo, que
    # tiene el contexto justo (presupuesto de herramientas, 6.20b).
    day: SkipJsonSchema[Literal["today", "tomorrow"] | None] = None


def tomorrow_only(result: ToolResult) -> ToolResult:
    """«¿Qué tiempo hará mañana?»: solo el de mañana (prueba del 2026-11-17)."""
    daily = result.data.get("daily") or {}
    place = str(result.data.get("city") or "")
    summary = _day_summary("Mañana", daily, 1)
    if not result.ok or not summary:
        return result
    highs = daily.get("temperature_2m_max") or []
    lows = daily.get("temperature_2m_min") or []
    shown = place[:1].upper() + place[1:]
    temps = (
        f" · máx. {round(float(highs[1]))}° mín. {round(float(lows[1]))}°"
        if len(highs) > 1 and len(lows) > 1 and highs[1] is not None and lows[1] is not None
        else ""
    )
    codes = daily.get("weather_code") or []
    sky = describe_code(codes[1]) if len(codes) > 1 else "variable"
    return result.model_copy(
        update={
            "message": f"Tiempo en {place}. {summary}.",
            "display": f"Mañana · {sky.capitalize()}",
            "secondary": f"{shown}{temps} · open-meteo.com",
        }
    )


class GetWeather(Tool[GetWeatherParams]):
    name = "get_weather"
    description = (
        "Consulta el tiempo y la previsión (Open-Meteo). "
        "Ej.: «¿va a llover mañana?», «¿qué temperatura hace en Madrid?» (city=Madrid)."
    )
    risk = Risk.GREEN
    game_policy = GamePolicy.ALLOWED
    category = Category.WEB
    params_model = GetWeatherParams
    observe = True
    timeout_s = 12.0  # dos peticiones (ciudad y previsión) de hasta 5 s cada una

    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        locator: Locator | None = None,
    ) -> None:
        self._transport = transport
        self._clock = clock
        self._locator = locator  # ubicación de Windows si no hay ciudad (None en pruebas)
        self._cache: dict[str, tuple[float, ToolResult]] = {}
        self._coords: dict[str, tuple[float, float, str]] = {}

    def clear_cache(self) -> None:
        self._cache.clear()
        self._coords.clear()

    async def run(self, params: GetWeatherParams, ctx: ToolContext) -> ToolResult:
        result = await self._forecast(params, ctx)
        return tomorrow_only(result) if params.day == "tomorrow" else result

    async def _forecast(self, params: GetWeatherParams, ctx: ToolContext) -> ToolResult:
        city = (params.city or ctx.settings.general.city).strip()
        here = None
        if not city and self._locator is not None:
            here = await self._locator.place()
        if not city and here is None:
            # En partida no se abre ninguna ventana encima del juego: solo se dice.
            playing = ctx.game is not None and ctx.game.active
            if ctx.open_nyx_settings is not None and not playing:
                await ctx.open_nyx_settings("general")
            return ToolResult.fail(
                "Dime tu ciudad en Ajustes → General",
                "o activa la ubicación de Windows",
            )

        if here is not None:  # sin ciudad: la ubicación de Windows, ya con su nombre
            key = f"@{here.latitude:.4f},{here.longitude:.4f}"
            self._coords[key] = (here.latitude, here.longitude, here.name)
        else:
            key = normalize(city)
        now = self._clock()
        cached = self._cache.get(key)
        if cached is not None and now - cached[0] < CACHE_TTL_S:
            return cached[1]

        try:
            async with httpx.AsyncClient(
                timeout=HTTP_TIMEOUT_S, transport=self._transport
            ) as client:
                if key not in self._coords:
                    geo = await client.get(
                        GEOCODE_URL,
                        params={"name": city, "language": "es", "count": 1},
                    )
                    geo.raise_for_status()
                    results = geo.json().get("results") or []
                    if not results:
                        return ToolResult.fail(
                            f"No encuentro la ciudad «{city}»",
                            "revisa el nombre en Ajustes → General",
                        )
                    first = results[0]
                    lat = float(first["latitude"])
                    lon = float(first["longitude"])
                    place = str(first.get("name") or city)
                    self._coords[key] = (lat, lon, place)
                else:
                    lat, lon, place = self._coords[key]

                forecast = await client.get(
                    FORECAST_URL,
                    params={
                        "latitude": lat,
                        "longitude": lon,
                        "current": (
                            "temperature_2m,apparent_temperature,weather_code,wind_speed_10m"
                        ),
                        "daily": (
                            "weather_code,temperature_2m_max,temperature_2m_min,"
                            "precipitation_probability_max"
                        ),
                        "timezone": "auto",
                        "forecast_days": 3,
                    },
                )
                forecast.raise_for_status()
                data = forecast.json()
        except httpx.HTTPError:
            log.warning("Fallo consultando Open-Meteo para %r", city, exc_info=True)
            return ToolResult.fail(
                "No tengo conexión para mirar el tiempo",
                "comprueba tu conexión a internet",
            )
        except KeyError, TypeError, ValueError:
            log.warning("Respuesta inesperada de Open-Meteo para %r", city, exc_info=True)
            return ToolResult.fail("No he podido leer la previsión del tiempo")

        result = format_weather(place, data)
        self._cache[key] = (now, result)
        return result
