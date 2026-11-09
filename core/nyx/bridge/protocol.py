"""Mensajes JSON entre el núcleo y la interfaz.

El tipo TypeScript equivalente está en ui/src/lib/protocol.ts: si cambias algo aquí,
cambia también allí y sube PROTOCOL_VERSION.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from nyx.events import NyxState

PROTOCOL_VERSION = 1


class _Msg(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# Interfaz → núcleo


class Hello(_Msg):
    """Primer mensaje obligatorio: autentica la conexión con el token de la sesión."""

    type: Literal["hello"] = "hello"
    token: str = Field(max_length=256)
    protocol: int


ClientMessage = Hello
client_adapter: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)


# Núcleo → interfaz


class Welcome(_Msg):
    type: Literal["welcome"] = "welcome"
    version: str
    protocol: int = PROTOCOL_VERSION


class StateMsg(_Msg):
    type: Literal["state"] = "state"
    state: NyxState


class LevelMsg(_Msg):
    """Nivel de audio a ~30 Hz para animar el indicador."""

    type: Literal["level"] = "level"
    rms: float = Field(ge=0.0, le=1.0)


class BubbleMsg(_Msg):
    type: Literal["bubble"] = "bubble"
    display: str
    secondary: str | None = None


class BubbleHideMsg(_Msg):
    type: Literal["bubble_hide"] = "bubble_hide"


ServerMessage = Annotated[
    Welcome | StateMsg | LevelMsg | BubbleMsg | BubbleHideMsg,
    Field(discriminator="type"),
]
server_adapter: TypeAdapter[ServerMessage] = TypeAdapter(ServerMessage)
