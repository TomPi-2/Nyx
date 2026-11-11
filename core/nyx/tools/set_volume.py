"""set_volume: volumen general o de una app, y silenciar (verde)."""

from __future__ import annotations

import asyncio
from typing import Self

from pydantic import Field, model_validator

from nyx.index.model import Kind
from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult
from nyx.winapi import media

DEFAULT_STEP = 10


class SetVolumeParams(Params):
    level: int | None = Field(default=None, ge=0, le=100, description="Nivel (0–100)")
    change: int | None = Field(default=None, ge=-100, le=100, description="Subir o bajar")
    mute: bool | None = Field(default=None, description="Silenciar")
    app: str | None = Field(default=None, max_length=100, description="Solo esta app")

    @model_validator(mode="after")
    def one_action(self) -> Self:
        if self.level is None and self.change is None and self.mute is None:
            raise ValueError("indica level, change o mute")
        if self.level is not None and self.change is not None:
            raise ValueError("level y change no van juntos")
        return self


class SetVolume(Tool[SetVolumeParams]):
    name = "set_volume"
    description = "Cambia o silencia el volumen. Ej.: «pon el volumen al 40» (level=40)."
    risk = Risk.GREEN
    game_policy = GamePolicy.ALLOWED
    category = Category.AUDIO
    params_model = SetVolumeParams

    async def run(self, params: SetVolumeParams, ctx: ToolContext) -> ToolResult:
        if params.app:
            return await self._app(params, ctx)
        level = params.level
        if params.change is not None:
            current, _ = await asyncio.to_thread(media.get_master)
            level = current + params.change
        volume, muted = await asyncio.to_thread(media.set_master, level, params.mute)
        text = "Silenciado" if muted else f"Volumen {volume}"
        return ToolResult(ok=True, message=text, data={"level": volume, "muted": muted})

    async def _app(self, params: SetVolumeParams, ctx: ToolContext) -> ToolResult:
        assert params.app is not None
        best = ctx.index.confident(ctx.index.resolve(params.app, {Kind.APP, Kind.GAME}))
        sessions = await asyncio.to_thread(media.app_sessions)
        wanted = best.entry.process if best and best.entry.process else None
        if wanted not in sessions:
            name = params.app.casefold().replace(" ", "")
            wanted = next((s for s in sessions if name in s.replace(" ", "")), None)
        if wanted is None:
            return ToolResult.fail(f"{params.app} no está sonando ahora")
        level = await asyncio.to_thread(
            media.set_app, wanted, params.level, params.mute, params.change
        )
        if level is None:
            return ToolResult.fail(f"{params.app} no está sonando ahora")
        name = best.entry.name if best else params.app
        shown = "silenciado" if params.mute else f"{level} %"
        return ToolResult(
            ok=True,
            message=f"Volumen de {name}: {shown}",
            display=f"{name} · {shown}",
            data={"level": level},
        )
