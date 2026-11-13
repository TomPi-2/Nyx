"""web_search (6.06): Wikipedia sin red real, navegador, sin conexión, caché y desactivado."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import httpx

from nyx.game.policy import GameGate
from nyx.settings.model import GameSettings
from nyx.tools.base import GamePolicy, Risk, ToolContext
from nyx.tools.web_search import WebSearch, WebSearchParams
from nyx.web.search import USER_AGENT, WikipediaSearch

SEARCH = {"query": {"search": [{"title": "Agujero negro"}]}}
SUMMARY = {
    "extract": "Un agujero negro es una región del espacio-tiempo de la que no escapa ni la luz.",
    "content_urls": {"desktop": {"page": "https://es.wikipedia.org/wiki/Agujero_negro"}},
}


def wiki(calls: list[httpx.Request], *, search: dict[str, Any] = SEARCH) -> WikipediaSearch:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if "api.php" in str(request.url):
            return httpx.Response(200, json=search)
        return httpx.Response(200, json=SUMMARY)

    return WikipediaSearch(transport=httpx.MockTransport(handler))


def test_metadata() -> None:
    assert WebSearch.risk is Risk.GREEN
    assert WebSearch.game_policy is GamePolicy.ALLOWED
    assert WebSearch.observe is True


async def test_summary_is_external_with_its_source(ctx: ToolContext) -> None:
    calls: list[httpx.Request] = []
    tool = WebSearch(engine=wiki(calls))
    result = await tool.run(WebSearchParams(query="agujero negro"), ctx)
    assert result.ok and result.secondary == "es.wikipedia.org"
    assert result.external is not None and "espacio-tiempo" in result.external
    assert "espacio-tiempo" not in result.message  # lo de fuera no va en el mensaje
    assert calls[0].headers["User-Agent"] == USER_AGENT
    # Caché: la misma consulta no vuelve a salir a internet.
    await tool.run(WebSearchParams(query="Agujero negro"), ctx)
    assert len(calls) == 2


async def test_nothing_found_offline_and_disabled(ctx: ToolContext) -> None:
    empty = WebSearch(engine=wiki([], search={"query": {"search": []}}))
    result = await empty.run(WebSearchParams(query="asdfgh"), ctx)
    assert not result.ok and "navegador" in (result.secondary or "")

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin red")

    offline = WebSearch(engine=WikipediaSearch(transport=httpx.MockTransport(down)))
    result = await offline.run(WebSearchParams(query="algo"), ctx)
    assert not result.ok and result.message == "No tengo conexión"

    ctx.settings.web.enabled = False
    result = await empty.run(WebSearchParams(query="algo"), ctx)
    assert not result.ok and "desactivado" in (result.secondary or "")


async def test_browser_but_not_over_a_game(ctx: ToolContext) -> None:
    opened: list[str] = []
    calls: list[httpx.Request] = []
    tool = WebSearch(engine=wiki(calls), opener=opened.append)
    result = await tool.run(WebSearchParams(query="recetas de lentejas", how="navegador"), ctx)
    assert result.ok and opened == ["https://www.google.com/search?q=recetas+de+lentejas"]

    gate = GameGate(GameSettings())
    gate.active = True
    playing = replace(ctx, game=gate)
    result = await tool.run(WebSearchParams(query="lentejas", how="navegador"), playing)
    assert len(opened) == 1 and result.external is not None  # en partida, el resumen
