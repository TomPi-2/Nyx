"""Ubicación de Windows para el tiempo cuando no hay ciudad en Ajustes (6.24).

- La posición sale de Windows (`Windows.Devices.Geolocation`): solo si el usuario tiene la
  ubicación activada y permitida para las apps de escritorio; si no, None y Nyx pide la ciudad
  como antes. Con la precisión más alta que dé Windows (el usuario lo pidió así).
- El nombre de la ciudad, con Nominatim (OpenStreetMap): una sola petición por posición, que
  se recuerda. Si falla, el tiempo funciona igual y el panel dice «tu ubicación».

Coordenadas solo a Open-Meteo (previsión) y Nominatim (nombre). Nada más sale del equipo.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

log = logging.getLogger(__name__)

REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
# Nominatim pide identificar la aplicación; nada personal (ni correo ni equipo).
USER_AGENT = "Nyx/0.6 (asistente de escritorio para Windows)"
POSITION_TIMEOUT_S = 6.0
HTTP_TIMEOUT_S = 5.0
REFRESH_S = 60 * 60.0  # la posición se vuelve a pedir como mucho cada hora
FALLBACK_NAME = "tu ubicación"


@dataclass(frozen=True, slots=True)
class Place:
    latitude: float
    longitude: float
    name: str  # ciudad, pueblo… o FALLBACK_NAME


async def windows_position(timeout_s: float = POSITION_TIMEOUT_S) -> tuple[float, float] | None:
    """(latitud, longitud) de Windows, o None si la ubicación está desactivada o no responde."""
    try:
        from winrt.windows.devices.geolocation import (
            GeolocationAccessStatus,
            Geolocator,
            PositionAccuracy,
        )

        if await Geolocator.request_access_async() != GeolocationAccessStatus.ALLOWED:
            log.info("Ubicación de Windows no permitida")
            return None
        locator = Geolocator()
        locator.desired_accuracy = PositionAccuracy.HIGH
        position = await asyncio.wait_for(locator.get_geoposition_async(), timeout_s)
        point = position.coordinate.point.position
        return float(point.latitude), float(point.longitude)
    except OSError, TimeoutError, ImportError, AttributeError:
        log.info("No se pudo leer la ubicación de Windows", exc_info=True)
        return None


def city_from_address(address: dict[str, Any]) -> str | None:
    """El nombre más útil para el tiempo: ciudad, pueblo, aldea o municipio."""
    for key in ("city", "town", "village", "municipality", "hamlet", "county"):
        value = address.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


async def reverse_city(
    latitude: float, longitude: float, transport: httpx.AsyncBaseTransport | None = None
) -> str | None:
    try:
        async with httpx.AsyncClient(
            timeout=HTTP_TIMEOUT_S, transport=transport, headers={"User-Agent": USER_AGENT}
        ) as client:
            reply = await client.get(
                REVERSE_URL,
                params={
                    "format": "jsonv2",
                    "lat": latitude,
                    "lon": longitude,
                    "zoom": 12,  # nivel de ciudad o pueblo
                    "accept-language": "es",
                },
            )
            reply.raise_for_status()
            return city_from_address(reply.json().get("address") or {})
    except httpx.HTTPError, ValueError, AttributeError:
        log.info("Nominatim no ha dado el nombre de la ciudad", exc_info=True)
        return None


class Locator:
    """La ubicación actual, pedida como mucho una vez por hora (y su nombre, una vez por sitio)."""

    def __init__(
        self,
        position: Callable[[], Awaitable[tuple[float, float] | None]] = windows_position,
        name: Callable[[float, float], Awaitable[str | None]] = reverse_city,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._position = position
        self._name = name
        self._clock = clock
        self._place: Place | None = None
        self._asked_at: float | None = None

    async def place(self) -> Place | None:
        now = self._clock()
        if self._asked_at is not None and now - self._asked_at < REFRESH_S:
            return self._place
        self._asked_at = now
        found = await self._position()
        if found is None:
            self._place = None
            return None
        lat, lon = found
        if self._place is not None and (self._place.latitude, self._place.longitude) == found:
            return self._place
        name = await self._name(lat, lon) or FALLBACK_NAME
        self._place = Place(lat, lon, name)
        return self._place
