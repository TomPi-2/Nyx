"""web_search: buscar en internet (0.6, tarea 6.06). Verde, `observe`, permitida en partida.

- «resumen»: en segundo plano, sin abrir nada: DuckDuckGo y el texto de las 2 mejores páginas,
  o Wikipedia si DuckDuckGo falla (ver `nyx/web/search.py`). Lo encontrado vuelve al LLM
  **marcado como contenido de fuera** y, en esa vuelta, **sin herramientas** (el pipeline no se
  las pasa): una web no puede hacer que Nyx actúe.
- «navegador»: abre la búsqueda en el navegador (`web.search_url`); en partida no se abre nada
  encima del juego, se busca el resumen.
- Sin conexión: «No tengo conexión» al momento. Caché de 15 minutos por consulta.
- `web.enabled` apagado: «No busco en internet: lo tienes desactivado».
- La burbuja enseña la fuente (dominio). A internet solo sale la consulta (SPEC §8).
"""

from __future__ import annotations

import asyncio
import logging
import time
import webbrowser
from collections.abc import Callable
from typing import Literal
from urllib.parse import quote_plus

import httpx
from pydantic import Field

from nyx.index.aliases import normalize
from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult
from nyx.web.search import OfflineError, SearchEngine, SearchHit, default_engine

log = logging.getLogger(__name__)

CACHE_TTL_S = 15 * 60.0
RESULTS = 2  # páginas que se leen y se pasan al modelo


class WebSearchParams(Params):
    query: str = Field(min_length=2, max_length=200, description="Lo que hay que buscar")
    how: Literal["resumen", "navegador"] = Field(
        default="resumen", description="resumen (lo cuenta Nyx) o navegador (lo abre)"
    )


class WebSearch(Tool[WebSearchParams]):
    name = "web_search"
    description = (
        "Busca en internet lo que no sabes o no recuerdas bien. "
        "Ej.: «busca quién fundó Tepnyx», «búscalo en el navegador» (how=navegador)."
    )
    risk = Risk.GREEN
    game_policy = GamePolicy.ALLOWED
    category = Category.WEB
    params_model = WebSearchParams
    observe = True
    timeout_s = 15.0

    def __init__(
        self,
        engine: SearchEngine | None = None,
        opener: Callable[[str], object] = webbrowser.open,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._engine = engine or default_engine()
        self._open = opener
        self._clock = clock
        self._cache: dict[str, tuple[float, list[SearchHit]]] = {}

    async def run(self, params: WebSearchParams, ctx: ToolContext) -> ToolResult:
        if not ctx.settings.web.enabled:
            return ToolResult.fail(
                "No busco en internet", "lo tienes desactivado en Ajustes → Privacidad"
            )
        playing = ctx.game is not None and ctx.game.active
        if params.how == "navegador" and not playing:
            url = ctx.settings.web.search_url.replace("{q}", quote_plus(params.query))
            if not url.startswith(("https://", "http://")):
                return ToolResult.fail(
                    "La dirección del buscador no es válida", "revísala en Ajustes"
                )
            await asyncio.to_thread(self._open, url)
            return ToolResult(
                ok=True,
                message=f"He abierto la búsqueda de «{params.query}» en el navegador.",
                observe=False,
                data={"how": "navegador"},
            )

        key = normalize(params.query)
        now = self._clock()
        cached = self._cache.get(key)
        if cached is not None and now - cached[0] < CACHE_TTL_S:
            hits = cached[1]
        else:
            try:
                hits = await self._engine.search(params.query, limit=RESULTS)
            except OfflineError:
                return ToolResult.fail("No tengo conexión", "no puedo buscar en internet")
            except httpx.HTTPError, ValueError, KeyError:
                log.warning("Fallo buscando %r", params.query, exc_info=True)
                return ToolResult.fail("No he podido buscarlo", "prueba otra vez en un rato")
            if not hits:
                return ToolResult.fail(
                    "No he encontrado nada", "puedo abrir la búsqueda en el navegador"
                )
            self._cache[key] = (now, hits)
        sources = list(dict.fromkeys(h.source for h in hits))
        return ToolResult(
            ok=True,
            message=f"He buscado «{params.query}» en internet (fuente: {', '.join(sources)}).",
            display=hits[0].title,
            secondary=" · ".join(sources),
            external="\n\n".join(f"[{h.source}] {h.title}: {h.summary}" for h in hits),
            data={"how": "resumen", "source": hits[0].source, "url": hits[0].url},
        )
