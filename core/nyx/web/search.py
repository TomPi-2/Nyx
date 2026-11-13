"""Búsqueda en internet (6.05 y 6.06).

Decisión de la 6.05 (tomada sin el usuario el 2026-11-13, pendiente de que la revise):

- **Wikipedia** (API de MediaWiki y resumen REST) para conocimiento: gratis, sin clave, estable y
  sus condiciones permiten usarla desde un programa (contenido CC BY-SA: se dice la fuente).
- **Abrir la búsqueda en el navegador** como respaldo siempre (`web.search_url`).
- Una API con clave para la actualidad (noticias, resultados) queda para cuando el usuario
  elija proveedor: la interfaz `SearchEngine` ya admite otro.

A internet solo sale la consulta (SPEC §8), con un User-Agent que identifica a Nyx sin ningún
dato del usuario (lo pide Wikimedia).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

import httpx

USER_AGENT = "Nyx/0.6 (asistente de escritorio para Windows)"
TIMEOUT_S = 5.0
MAX_SUMMARY = 3000


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


_TAGS = re.compile(r"<[^>]+>")


class WikipediaSearch:
    """Busca en Wikipedia y devuelve el resumen de los mejores artículos."""

    def __init__(self, lang: str = "es", transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.lang = lang
        self._transport = transport

    @property
    def source(self) -> str:
        return f"{self.lang}.wikipedia.org"

    async def search(self, query: str, limit: int = 1) -> list[SearchHit]:
        base = f"https://{self.source}"
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(TIMEOUT_S, connect=2.0),
                transport=self._transport,
                headers={"User-Agent": USER_AGENT},
            ) as client:
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
                hits: list[SearchHit] = []
                for title in titles[:limit]:
                    page = await client.get(
                        f"{base}/api/rest_v1/page/summary/{title.replace(' ', '_')}"
                    )
                    if page.status_code != 200:
                        continue
                    data = page.json()
                    summary = _TAGS.sub("", str(data.get("extract") or "")).strip()
                    if not summary:
                        continue
                    url = (
                        data.get("content_urls", {}).get("desktop", {}).get("page")
                        or f"{base}/wiki/{title.replace(' ', '_')}"
                    )
                    hits.append(SearchHit(title, str(url), summary[:MAX_SUMMARY], self.source))
                return hits
        except httpx.ConnectError as exc:
            raise OfflineError from exc
