"""Búsqueda en internet (6.05 y 6.06; DuckDuckGo desde el 2026-11-13, decisión del usuario).

En segundo plano, sin abrir el navegador, gratis y sin clave:

1. **DuckDuckGo** (su versión sencilla en HTML, `html.duckduckgo.com`) da los resultados de
   toda la web. No es un servicio oficial para programas: puede cambiar o bloquear sin
   aviso. Por eso se pide como cualquier visitante honrado (User-Agent de Nyx, sin hacerse
   pasar por un navegador) y, si falla, se sigue con lo siguiente. Revisarlo antes de la beta.
2. De los mejores resultados se **lee el texto de la página** (párrafos y listas, sin menús ni
   scripts). Si un resultado es de Wikipedia, se usa su resumen oficial (más limpio).
3. Si DuckDuckGo falla o no da nada, **Wikipedia** sola (API de MediaWiki: gratis, sin clave y
   sus condiciones permiten usarla desde un programa; contenido CC BY-SA, se dice la fuente).
4. El navegador (`web.search_url`) queda como último recurso, en la herramienta.

A internet sale la consulta (a DuckDuckGo o Wikipedia) y las visitas a las páginas leídas
(SPEC §8), con un User-Agent que identifica a Nyx sin ningún dato del usuario. Lo leído es
contenido de fuera: la herramienta lo marca así y el modelo lo recibe sin herramientas.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from nyx.index.aliases import normalize

log = logging.getLogger(__name__)

USER_AGENT = "Nyx/0.6 (asistente de escritorio para Windows)"
TIMEOUT_S = 5.0
MAX_SUMMARY = 3000  # por resultado
MAX_PAGE_BYTES = 1_500_000  # una página más grande no se lee entera
DDG_URL = "https://html.duckduckgo.com/html/"


@dataclass(frozen=True, slots=True)
class SearchHit:
    title: str
    url: str
    summary: str
    source: str  # dominio, para la burbuja («es.wikipedia.org»)


class SearchEngine(Protocol):
    async def search(self, query: str, limit: int = 1) -> list[SearchHit]: ...


class OfflineError(Exception):
    """Sin conexión: se dice al momento, sin esperar al tiempo límite."""


class SearchError(Exception):
    """El buscador no ha respondido como se esperaba (cambio de formato, bloqueo…)."""


_TAGS = re.compile(r"<[^>]+>")


def _client(transport: httpx.AsyncBaseTransport | None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(TIMEOUT_S, connect=2.0),
        transport=transport,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "es-ES,es;q=0.9"},
        follow_redirects=True,
        max_redirects=3,
    )


def domain(url: str) -> str:
    host = urlparse(url).hostname or ""
    return host.removeprefix("www.")


# --- Wikipedia ---


_STOPWORDS = frozenset({
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "al", "a", "en", "y",
    "o", "que", "como", "para", "por", "con", "sin", "se",
})  # fmt: skip


def _words(text: str) -> set[str]:
    return {w for w in normalize(text).split() if w not in _STOPWORDS}


class WikipediaSearch:
    """Busca en Wikipedia y devuelve el resumen de los mejores artículos.

    `strict`: solo los artículos cuyo título está en la pregunta («Imprenta» para «¿quién
    inventó la imprenta?»). Como respaldo de DuckDuckGo, mejor nada que un artículo que no
    viene a cuento (para «cómo poner la barra de tareas a la izquierda» salía «Forth»).
    """

    def __init__(
        self,
        lang: str = "es",
        transport: httpx.AsyncBaseTransport | None = None,
        *,
        strict: bool = False,
    ) -> None:
        self.lang = lang
        self._transport = transport
        self.strict = strict

    @property
    def source(self) -> str:
        return f"{self.lang}.wikipedia.org"

    async def search(self, query: str, limit: int = 1) -> list[SearchHit]:
        base = f"https://{self.source}"
        try:
            async with _client(self._transport) as client:
                found = await client.get(
                    f"{base}/w/api.php",
                    params={
                        "action": "query",
                        "list": "search",
                        "srsearch": query,
                        "srlimit": limit,
                        "format": "json",
                        "utf8": 1,
                    },
                )
                found.raise_for_status()
                titles = [r["title"] for r in found.json().get("query", {}).get("search", [])]
                if self.strict:
                    asked = _words(query)
                    titles = [t for t in titles if _words(t) and _words(t) <= asked]
                hits: list[SearchHit] = []
                for title in titles[:limit]:
                    if (hit := await self.summary(client, title)) is not None:
                        hits.append(hit)
                return hits
        except httpx.ConnectError as exc:
            raise OfflineError from exc

    async def summary(self, client: httpx.AsyncClient, title: str) -> SearchHit | None:
        """El resumen oficial de un artículo (título tal cual o con guiones bajos)."""
        base = f"https://{self.source}"
        page = await client.get(f"{base}/api/rest_v1/page/summary/{title.replace(' ', '_')}")
        if page.status_code != 200:
            return None
        data = page.json()
        summary = _TAGS.sub("", str(data.get("extract") or "")).strip()
        if not summary:
            return None
        url = (
            data.get("content_urls", {}).get("desktop", {}).get("page")
            or f"{base}/wiki/{title.replace(' ', '_')}"
        )
        name = str(data.get("title") or title.replace("_", " "))
        return SearchHit(name, str(url), summary[:MAX_SUMMARY], self.source)


# --- DuckDuckGo ---


@dataclass(frozen=True, slots=True)
class Result:
    title: str
    url: str
    snippet: str


class _ResultsParser(HTMLParser):
    """Los resultados de html.duckduckgo.com: enlace `result__a` y texto `result__snippet`.
    Los anuncios se caen solos: su enlace va a `duckduckgo.com/y.js`, sin destino (`real_url`)."""

    def __init__(self) -> None:
        super().__init__()
        self.results: list[Result] = []
        self._field: str | None = None
        self._href = ""
        self._title: list[str] = []
        self._snippet: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = (dict(attrs).get("class") or "").split()
        if tag == "a" and "result__a" in classes:
            self._flush()
            self._field, self._href = "title", dict(attrs).get("href") or ""
        elif "result__snippet" in classes:
            self._field = "snippet"

    def handle_endtag(self, tag: str) -> None:
        if tag in ("a", "td", "div") and self._field is not None:
            self._field = None

    def handle_data(self, data: str) -> None:
        if self._field is not None:
            (self._title if self._field == "title" else self._snippet).append(data)

    def _flush(self) -> None:
        url = real_url(self._href)
        title = " ".join("".join(self._title).split())
        if url and title:
            self.results.append(Result(title, url, " ".join("".join(self._snippet).split())))
        self._title, self._snippet, self._href = [], [], ""

    def close(self) -> None:
        super().close()
        self._flush()


def real_url(href: str) -> str | None:
    """El destino de un enlace de resultados («//duckduckgo.com/l/?uddg=…»); solo http(s)."""
    href = unescape(href)
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if parsed.hostname and parsed.hostname.endswith("duckduckgo.com"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        if not target:
            return None  # enlaces internos (anuncios, más resultados)
        href = target
    return href if urlparse(href).scheme in ("http", "https") else None


def parse_results(html: str) -> list[Result]:
    parser = _ResultsParser()
    parser.feed(html)
    parser.close()
    return parser.results


class _TextParser(HTMLParser):
    """El texto que se lee de una página: párrafos, títulos y elementos de lista, fuera de
    menús, cabeceras, pies, formularios y scripts."""

    _SKIP = frozenset({"script", "style", "nav", "header", "footer", "aside", "form", "noscript",
                       "svg", "button", "select", "template", "iframe"})  # fmt: skip
    _BLOCKS = frozenset({"p", "li", "h1", "h2", "h3", "td", "dd", "blockquote"})

    def __init__(self) -> None:
        super().__init__()
        self.blocks: list[str] = []
        self._skip = 0
        self._links = 0
        self._open: list[str] = []
        self._buf: list[str] = []
        self._linked = 0  # caracteres del bloque que están dentro de un enlace

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP:
            self._skip += 1
        elif tag == "a":
            self._links += 1
        elif tag in self._BLOCKS:
            self._end_block()
            self._open.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag == "a":
            self._links = max(0, self._links - 1)
        elif tag in self._BLOCKS:
            self._end_block()

    def handle_data(self, data: str) -> None:
        if not self._skip and self._open:
            self._buf.append(data)
            if self._links:
                self._linked += len(data.strip())

    def _end_block(self) -> None:
        text = " ".join("".join(self._buf).split())
        kind = self._open.pop() if self._open else ""
        linked, self._linked, self._buf = self._linked, 0, []
        # Casi todo enlaces: un menú o una lista de artículos relacionados, no el contenido.
        if not text or linked > 0.6 * len(text):
            return
        # Un párrafo corto suele ser ruido (botones, avisos); en las listas (ingredientes,
        # pasos) cuenta todo lo que tenga algo de texto.
        if len(text) >= 40 or (kind in ("li", "h1", "h2", "h3") and len(text) >= 3):
            self.blocks.append(text)


def page_text(html: str, limit: int = MAX_SUMMARY) -> str:
    parser = _TextParser()
    parser.feed(html)
    parser.close()
    out: list[str] = []
    size = 0
    for block in dict.fromkeys(parser.blocks):  # sin repetidos, en orden
        if size + len(block) > limit:
            break
        out.append(block)
        size += len(block) + 1
    return "\n".join(out)


async def fetch_page(client: httpx.AsyncClient, url: str) -> str | None:
    """El HTML de una página (solo http/https y HTML, hasta MAX_PAGE_BYTES), o None."""
    if urlparse(url).scheme not in ("http", "https"):
        return None
    try:
        async with client.stream("GET", url) as resp:
            kind = resp.headers.get("content-type", "")
            if resp.status_code != 200 or "html" not in kind:
                return None
            chunks: list[bytes] = []
            size = 0
            async for chunk in resp.aiter_bytes():
                chunks.append(chunk)
                size += len(chunk)
                if size >= MAX_PAGE_BYTES:
                    break
            return b"".join(chunks).decode(resp.encoding or "utf-8", errors="replace")
    except httpx.HTTPError:
        log.info("No se pudo leer %s", url, exc_info=True)
        return None


class DuckDuckGoSearch:
    """Resultados de DuckDuckGo y el texto de las mejores páginas (ver el docstring)."""

    source = "duckduckgo.com"

    def __init__(
        self,
        region: str = "es-es",
        transport: httpx.AsyncBaseTransport | None = None,
        wikipedia: WikipediaSearch | None = None,
    ) -> None:
        self.region = region
        self._transport = transport
        self._wikipedia = wikipedia or WikipediaSearch(transport=transport)

    async def results(self, client: httpx.AsyncClient, query: str) -> list[Result]:
        # Como lo envía su propio formulario (POST): por GET, DuckDuckGo bloqueaba a los pocos
        # minutos («anomaly», HTTP 202) y por POST no (probado el 2026-11-13).
        resp = await client.post(DDG_URL, data={"q": query, "kl": self.region})
        if resp.status_code != 200:
            raise SearchError(f"DuckDuckGo: HTTP {resp.status_code}")
        found = parse_results(resp.text)
        if not found and "result__a" not in resp.text and "No results" not in resp.text:
            raise SearchError("DuckDuckGo: respuesta sin resultados reconocibles")
        return found

    async def search(self, query: str, limit: int = 1) -> list[SearchHit]:
        try:
            async with _client(self._transport) as client:
                found = await self.results(client, query)
                picked = found[: max(limit, 1) + 2]  # alguno puede no leerse
                read = await asyncio.gather(*(self._read(client, r) for r in picked))
                return [hit for hit in read if hit is not None][:limit]
        except httpx.ConnectError as exc:
            raise OfflineError from exc

    async def _read(self, client: httpx.AsyncClient, result: Result) -> SearchHit | None:
        host = domain(result.url)
        if host.endswith("wikipedia.org") and "/wiki/" in result.url:
            title = unquote(result.url.split("/wiki/", 1)[1].split("#", 1)[0].split("?", 1)[0])
            wiki = WikipediaSearch(lang=host.split(".", 1)[0], transport=self._transport)
            try:
                hit = await wiki.summary(client, title)
            except (httpx.HTTPError, ValueError):
                hit = None
            if hit is not None:
                return hit
        html = await fetch_page(client, result.url)
        text = page_text(html) if html else ""
        summary = text or result.snippet
        if not summary:
            return None
        return SearchHit(result.title, result.url, summary[:MAX_SUMMARY], host)


class ChainSearch:
    """El primer buscador que dé algo: DuckDuckGo y, si falla o no da nada, Wikipedia."""

    def __init__(self, *engines: SearchEngine) -> None:
        self.engines = engines

    async def search(self, query: str, limit: int = 1) -> list[SearchHit]:
        offline = False
        for engine in self.engines:
            try:
                hits = await engine.search(query, limit)
            except OfflineError:
                offline = True
                continue
            except (SearchError, httpx.HTTPError, ValueError, KeyError):
                log.warning("Fallo buscando con %s", type(engine).__name__, exc_info=True)
                continue
            if hits:
                return hits
        if offline:
            raise OfflineError
        return []


def default_engine() -> SearchEngine:
    return ChainSearch(DuckDuckGoSearch(), WikipediaSearch(strict=True))
