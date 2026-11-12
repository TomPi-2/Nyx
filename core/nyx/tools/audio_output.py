"""audio_output: abre los ajustes de sonido de Windows para elegir la salida de audio (6.12).

Windows no ofrece una API pública documentada para cambiar el dispositivo de salida
predeterminado (`pycaw` solo lo hace mediante `IPolicyConfig` / `CPolicyConfigClient`, que son
interfaces COM sin documentar). Por eso abre `ms-settings:sound` y se lo explica al usuario.
"""

from __future__ import annotations

import asyncio

from pydantic import Field

from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult
from nyx.winapi import focus, launch


class AudioOutputParams(Params):
    device: str = Field(default="", max_length=100, description="Dispositivo pedido (si se indica)")


class AudioOutput(Tool[AudioOutputParams]):
    name = "audio_output"
    description = (
        "Abre ajustes de sonido para cambiar la salida (Windows no deja hacerlo solo). "
        "Ej.: «pon el sonido en los auriculares»."
    )
    risk = Risk.GREEN
    game_policy = GamePolicy.DEFERRED
    category = Category.AUDIO
    params_model = AudioOutputParams
    observe = True

    async def run(self, params: AudioOutputParams, ctx: ToolContext) -> ToolResult:
        try:
            before = await asyncio.to_thread(focus.snapshot)
            await asyncio.to_thread(launch.shell_open, "ms-settings:sound")
        except OSError as e:
            return ToolResult.fail("No he podido abrir los ajustes de sonido", str(e))
        focus.request("Configuración", None, before, reuse_after_s=1.0)
        target = f" para elegir {params.device}" if params.device else ""
        return ToolResult(
            ok=True,
            message=(
                "Windows no permite cambiar la salida de audio automáticamente; "
                f"he abierto los ajustes de sonido{target}."
            ),
            display="Ajustes de sonido",
            secondary="Elige el dispositivo ahí (Windows no deja hacerlo solo)",
            data={"opened": "ms-settings:sound", "device": params.device},
        )
