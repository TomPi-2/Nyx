"""Ubicación de Windows y nombre de la ciudad (6.24), sin tocar Windows ni la red."""

from __future__ import annotations

import httpx

from nyx.winapi.location import (
    FALLBACK_NAME,
    REFRESH_S,
    USER_AGENT,
    Locator,
    city_from_address,
    reverse_city,
)


def test_city_from_address_prefers_city_then_town() -> None:
    assert city_from_address({"city": "Valencia", "county": "Horta"}) == "Valencia"
    assert city_from_address({"village": "Bocairent", "county": "Vall"}) == "Bocairent"
    assert city_from_address({"road": "Calle Mayor"}) is None


async def test_reverse_city_identifies_nyx_and_asks_in_spanish() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"address": {"town": "Gandia"}})

    assert await reverse_city(38.97, -0.18, httpx.MockTransport(handler)) == "Gandia"
    assert seen[0].headers["User-Agent"] == USER_AGENT
    assert "accept-language=es" in str(seen[0].url)


async def test_reverse_city_failure_is_none() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(503))
    assert await reverse_city(38.97, -0.18, transport) is None


async def test_locator_asks_at_most_once_an_hour_and_names_each_place_once() -> None:
    now = [0.0]
    positions = [(1.0, 2.0), (1.0, 2.0), (3.0, 4.0)]
    asked_names: list[tuple[float, float]] = []

    async def position() -> tuple[float, float]:
        return positions.pop(0)

    async def name(lat: float, lon: float) -> str | None:
        asked_names.append((lat, lon))
        return None if lat == 3.0 else "Sitio"

    locator = Locator(position, name, clock=lambda: now[0])
    first = await locator.place()
    assert first is not None and first.name == "Sitio"
    assert await locator.place() is first  # dentro de la hora: no se vuelve a pedir
    now[0] += REFRESH_S
    assert await locator.place() is first  # misma posición: no se vuelve a nombrar
    now[0] += REFRESH_S
    moved = await locator.place()
    assert moved is not None and moved.name == FALLBACK_NAME
    assert asked_names == [(1.0, 2.0), (3.0, 4.0)]
