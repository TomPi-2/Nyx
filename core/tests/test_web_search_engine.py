"""Buscador en segundo plano (2026-11-13): DuckDuckGo, leer páginas y Wikipedia de respaldo.

Todo con una red falsa (`httpx.MockTransport`): ninguna prueba sale a internet.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from nyx.tools.base import ToolContext
from nyx.tools.web_search import WebSearch, WebSearchParams
from nyx.web import search as search_module
from nyx.web.search import (
    USER_AGENT,
    ChainSearch,
    DuckDuckGoSearch,
    OfflineError,
    WikipediaSearch,
    local_address,
    page_text,
    parse_results,
    real_url,
)

RESULTS = """
<div class="result results_links result--ad">
  <a class="result__a" href="//duckduckgo.com/y.js?ad_domain=tienda.com&amp;u3=x">Compra ya</a>
  <a class="result__snippet" href="//duckduckgo.com/y.js?x">Oferta</a>
</div>
<div class="result results_links">
  <h2 class="result__title"><a rel="nofollow" class="result__a"
    href="//duckduckgo.com/l/?uddg=https%3A%2F%2Frecetas.example%2Ftortilla&amp;rut=abc">Tortilla
    de <b>patatas</b> jugosa</a></h2>
  <a class="result__snippet" href="//duckduckgo.com/l/?uddg=x">La receta de siempre, paso a
    paso.</a>
</div>
<div class="result results_links">
  <a class="result__a"
    href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fes.wikipedia.org%2Fwiki%2FTortilla_de_patatas"
    >Tortilla de patatas - Wikipedia</a>
  <a class="result__snippet">Plato típico español.</a>
</div>
<div class="result results_links">
  <a class="result__a"
    href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fdocs.example%2Freceta.pdf">PDF</a>
  <a class="result__snippet">La receta en PDF, con fotos de cada paso.</a>
</div>
"""

PAGE = """<html><head><script>alert('hola')</script><style>p{}</style></head><body>
<nav><ul><li><a href="/">Inicio</a></li><li><a href="/x">Recetas</a></li></ul></nav>
<ul class="menu"><li><a href="/a">Menú</a></li><li><a href="/b">Nuevo</a></li></ul>
<h1>Tortilla de patatas</h1>
<p>Una tortilla jugosa necesita patatas pochadas a fuego lento y huevos bien batidos.</p>
<p>Corto.</p>
<ul><li>4 huevos</li><li>3 patatas</li><li>Sal</li></ul>
<p>Una tortilla jugosa necesita patatas pochadas a fuego lento y huevos bien batidos.</p>
<footer><p>Todos los derechos reservados a quien corresponda, en cualquier caso.</p></footer>
</body></html>"""

WIKI_SUMMARY = {
    "title": "Tortilla de patatas",
    "extract": "La tortilla de patatas es una tortilla con huevo y patatas.",
    "content_urls": {"desktop": {"page": "https://es.wikipedia.org/wiki/Tortilla_de_patatas"}},
}


def web(calls: list[httpx.Request], ddg_status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        url = str(request.url)
        if "html.duckduckgo.com" in url:
            return httpx.Response(ddg_status, text=RESULTS if ddg_status == 200 else "anomaly")
        if "recetas.example" in url:
            return httpx.Response(200, text=PAGE, headers={"content-type": "text/html"})
        if "docs.example" in url:
            return httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"})
        if "/page/summary/" in url:
            return httpx.Response(200, json=WIKI_SUMMARY)
        if "api.php" in url:
            titles = [{"title": "Forth"}, {"title": "Imprenta"}]
            return httpx.Response(200, json={"query": {"search": titles}})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_results_skip_ads_and_decode_the_real_address() -> None:
    found = parse_results(RESULTS)
    assert [r.url for r in found] == [
        "https://recetas.example/tortilla",
        "https://es.wikipedia.org/wiki/Tortilla_de_patatas",
        "https://docs.example/receta.pdf",
    ]
    assert found[0].title == "Tortilla de patatas jugosa"
    assert found[0].snippet == "La receta de siempre, paso a paso."


@pytest.mark.parametrize(
    ("href", "url"),
    [
        ("//duckduckgo.com/l/?uddg=https%3A%2F%2Fa.es%2Fb&amp;rut=1", "https://a.es/b"),
        ("//duckduckgo.com/y.js?ad_domain=x", None),
        ("//duckduckgo.com/l/?uddg=javascript%3Aalert(1)", None),
        ("//duckduckgo.com/l/?uddg=file%3A%2F%2F%2FC%3A%2Fx", None),
        ("https://directo.es/x", "https://directo.es/x"),
    ],
)
def test_real_url_only_web_addresses(href: str, url: str | None) -> None:
    assert real_url(href) == url


def test_page_text_keeps_the_content_and_drops_the_rest() -> None:
    text = page_text(PAGE)
    lines = text.splitlines()
    assert lines[0] == "Tortilla de patatas"
    assert "4 huevos" in lines and "3 patatas" in lines and "Sal" in lines
    assert sum("pochadas" in line for line in lines) == 1  # sin repetidos
    for noise in ("alert", "Inicio", "Menú", "Nuevo", "Corto.", "derechos"):
        assert noise not in text, noise
    assert len(page_text(PAGE, limit=30)) <= 30


async def test_duckduckgo_reads_pages_and_uses_the_wikipedia_summary() -> None:
    calls: list[httpx.Request] = []
    hits = await DuckDuckGoSearch(transport=web(calls)).search("tortilla de patatas", limit=3)
    assert [h.source for h in hits] == ["recetas.example", "es.wikipedia.org", "docs.example"]
    assert "pochadas" in hits[0].summary and "4 huevos" in hits[0].summary
    assert hits[1].summary == WIKI_SUMMARY["extract"]  # el resumen oficial, no la página
    assert hits[2].summary == "La receta en PDF, con fotos de cada paso."  # no es HTML
    assert all(c.headers["User-Agent"] == USER_AGENT for c in calls)
    ddg = next(c for c in calls if "duckduckgo" in str(c.url))
    assert ddg.method == "POST" and ddg.content == b"q=tortilla+de+patatas&kl=es-es"


async def test_blocked_duckduckgo_falls_back_to_wikipedia_only_if_it_fits() -> None:
    calls: list[httpx.Request] = []
    transport = web(calls, ddg_status=202)  # la comprobación antirrobots de DuckDuckGo
    chain = ChainSearch(
        DuckDuckGoSearch(transport=transport), WikipediaSearch(transport=transport, strict=True)
    )
    hits = await chain.search("¿quién inventó la imprenta?", 2)
    # «Forth» no viene a cuento; «Imprenta» sí (el resumen falso dice otra cosa: da igual).
    assert len(hits) == 1
    assert [str(c.url).rsplit("/", 1)[-1] for c in calls if "/summary/" in str(c.url)] == [
        "Imprenta"
    ]


async def test_offline_everywhere() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin red")

    transport = httpx.MockTransport(down)
    chain = ChainSearch(DuckDuckGoSearch(transport=transport), WikipediaSearch(transport=transport))
    with pytest.raises(OfflineError):
        await chain.search("algo", 1)


async def test_tool_passes_two_sources_as_external_content(ctx: ToolContext) -> None:
    tool = WebSearch(engine=DuckDuckGoSearch(transport=web([])))
    result = await tool.run(WebSearchParams(query="tortilla de patatas"), ctx)
    assert result.ok and result.display == "Tortilla de patatas jugosa"
    assert result.secondary == "recetas.example · es.wikipedia.org"
    assert result.external is not None
    assert result.external.startswith("[recetas.example] Tortilla de patatas jugosa:")
    assert "[es.wikipedia.org] Tortilla de patatas:" in result.external
    assert "pochadas" not in result.message  # lo de fuera no va en el mensaje


# --- revisión de la 6.19: nada de la red local y cada página con su tiempo ---


@pytest.mark.parametrize(
    ("url", "local"),
    [
        ("http://localhost:8765/", True),
        ("http://127.0.0.1/", True),
        ("http://192.168.1.1/reiniciar", True),
        ("http://10.0.0.5/", True),
        ("http://169.254.1.1/", True),
        ("http://[::1]/", True),
        ("http://router/", True),
        ("http://impresora.local/", True),
        ("http://nas.home.arpa/", True),
        ("https://es.wikipedia.org/wiki/Imprenta", False),
        ("https://8.8.8.8/", False),
        ("https://recetas.example/tortilla", False),
    ],
)
def test_local_address(url: str, local: bool) -> None:
    assert local_address(url) is local


async def test_a_page_cannot_send_nyx_to_the_home_network() -> None:
    calls: list[httpx.Request] = []
    inner = web(calls)

    def handler(request: httpx.Request) -> httpx.Response:
        if "recetas.example" in str(request.url):
            calls.append(request)
            return httpx.Response(302, headers={"location": "http://192.168.1.1/reiniciar"})
        return inner.handle_request(request)

    hits = await DuckDuckGoSearch(transport=httpx.MockTransport(handler)).search("tortilla", 1)
    assert all("192.168" not in str(c.url) for c in calls)  # la redirección no se sigue
    assert hits[0].summary == "La receta de siempre, paso a paso."  # el resumen del buscador


async def test_a_slow_page_does_not_hold_the_search(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(search_module, "PAGE_DEADLINE_S", 0.05)
    inner = web([])

    async def handler(request: httpx.Request) -> httpx.Response:
        if "recetas.example" in str(request.url):
            await asyncio.sleep(2)
        return inner.handle_request(request)

    hits = await DuckDuckGoSearch(transport=httpx.MockTransport(handler)).search("tortilla", 3)
    assert hits[0].summary == "La receta de siempre, paso a paso."
    assert hits[1].summary == WIKI_SUMMARY["extract"]
