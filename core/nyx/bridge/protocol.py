"""Mensajes JSON entre el núcleo y la interfaz.

El tipo TypeScript equivalente está en ui/src/lib/protocol.ts: si cambias algo aquí,
cambia también allí y sube PROTOCOL_VERSION.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from nyx.events import NyxState

PROTOCOL_VERSION = 5


class _Msg(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# Interfaz → núcleo


class Hello(_Msg):
    """Primer mensaje obligatorio: autentica la conexión con el token de la sesión."""

    type: Literal["hello"] = "hello"
    token: str = Field(max_length=256)
    protocol: int


class TextInput(_Msg):
    """Petición escrita en el campo de texto."""

    type: Literal["text"] = "text"
    text: str = Field(min_length=1, max_length=2000)


class TalkKeyMsg(_Msg):
    """Atajo de hablar (pulsar o mantener)."""

    type: Literal["talk"] = "talk"
    pressed: bool


class ActionMsg(_Msg):
    """Botón pulsado en una burbuja."""

    type: Literal["action"] = "action"
    id: str = Field(min_length=1, max_length=64)


ClientMessage = Annotated[Hello | TextInput | TalkKeyMsg | ActionMsg, Field(discriminator="type")]
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


class ActionButton(_Msg):
    id: str
    label: str
    primary: bool = False


class BubbleMsg(_Msg):
    type: Literal["bubble"] = "bubble"
    display: str
    secondary: str | None = None
    actions: list[ActionButton] = []
    alert: bool = False  # v4: alarmas y avisos (la interfaz lanza la notificación de Windows)


class BubbleHideMsg(_Msg):
    type: Literal["bubble_hide"] = "bubble_hide"


class GameMsg(_Msg):
    """v5: partida en marcha y «Nyx en partida» (la interfaz no aparece sobre el juego)."""

    type: Literal["game"] = "game"
    active: bool
    mode: Literal["off", "voice", "normal"] = "voice"


ServerMessage = Annotated[
    Welcome | StateMsg | LevelMsg | BubbleMsg | BubbleHideMsg | GameMsg,
    Field(discriminator="type"),
]
server_adapter: TypeAdapter[ServerMessage] = TypeAdapter(ServerMessage)
