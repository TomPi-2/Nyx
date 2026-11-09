"""open_url: abre una web en el navegador predeterminado (verde)."""

from __future__ import annotations

import asyncio
import re
from urllib.parse import urlparse

from pydantic import Field

from nyx.index.model import Kind
from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult
from nyx.tools.resolve import pick
from nyx.winapi import focus, launch

# «claude.ai», «www.marca.com», «elpais.es/deportes»…
_DOMAIN = re.compile(r"^(?:https?://)?(?:[\w-]+\.)+[a-z]{2,}(?:[/?#]\S*)?$", re.IGNORECASE)


class OpenUrlParams(Params):
    target: str = Field(
        min_length=1, max_length=2000, description="Nombre de la web (YouTube, Gmail…) o dirección"
    )
    focus: bool = Field(
        default=True,
        description="Traer la ventana al frente; false si piden abrirlo en segundo plano",
    )


def to_url(target: str) -> str | None:
    """Dirección http(s) si `target` lo parece; nunca otros esquemas (file:, javascript:…)."""
    text = target.strip().replace(" punto ", ".").replace(" ", "")
    if not _DOMAIN.match(text):
        return None
    url = text if text.lower().startswith(("http://", "https://")) else f"https://{text}"
    return url if urlparse(url).scheme in ("http", "https") else None


class OpenUrl(Tool[OpenUrlParams]):
    name = "open_url"
    description = (
        "Abre una página web en el navegador. Ej.: «abre YouTube», «abre Claude en el "
        "navegador», «entra en marca.com»."
    )
    risk = Risk.GREEN
    game_policy = GamePolicy.DEFERRED
    category = Category.WEB
    params_model = OpenUrlParams

    async def run(self, params: OpenUrlParams, ctx: ToolContext) -> ToolResult:
        url = to_url(params.target)
        key = None
        name = params.target
        if url is None:
            found = pick(ctx.index, params.target, {Kind.WEB}, "la web")
            if isinstance(found, ToolResult):
                return found
            url, key, name = found.entry.launch.value, found.entry.key, found.entry.name
        try:
            before = await asyncio.to_thread(focus.snapshot) if params.focus else set()
            await asyncio.to_thread(launch.shell_open, url)
        except OSError as e:
            return ToolResult.fail(f"No he podido abrir {name}", str(e))
        if key:
            ctx.index.record_use(key)
        if params.focus:
            # Suele abrirse en una pestaña del navegador que ya estaba: se activa enseguida.
            focus.request(name, focus.default_browser_process(), before, reuse_after_s=0.8)
        return ToolResult(ok=True, message=f"Abriendo {name}", data={"url": url})
