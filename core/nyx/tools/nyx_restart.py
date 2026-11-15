"""nyx_restart: «reiníciate» reinicia Nyx (su núcleo), nunca el PC. Verde; en partida, al
terminar (cargar los modelos otra vez cuesta FPS).

Visto en los registros del 2026-11-15: «reiníciate» llegaba al modelo, que elegía reiniciar el
ordenador. Ahora lo resuelve el router y Nyx se reinicia como con bandeja → Reiniciar. Se
espera un momento para que dé tiempo a decir que se reinicia.
"""

from __future__ import annotations

import asyncio

from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult

#: Lo que se espera antes de reiniciar, para que se oiga la respuesta.
DELAY_S = 2.5


class NyxRestart(Tool[Params]):
    name = "nyx_restart"
    description = "Reinicia Nyx (no el ordenador). Ej.: «reiníciate»."
    risk = Risk.GREEN
    game_policy = GamePolicy.DEFERRED
    category = Category.SYSTEM
    params_model = Params

    async def run(self, params: Params, ctx: ToolContext) -> ToolResult:
        restart = ctx.restart_nyx
        if restart is None:
            return ToolResult.fail("No puedo reiniciarme ahora", "sin interfaz")

        async def later() -> None:
            await asyncio.sleep(DELAY_S)
            await restart()

        task = asyncio.create_task(later())
        _pending.add(task)
        task.add_done_callback(_pending.discard)
        return ToolResult(ok=True, message="Me reinicio, vuelvo en unos segundos", speak=True)


_pending: set[asyncio.Task[None]] = set()
