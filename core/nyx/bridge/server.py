"""UIBridge: servidor WebSocket local que envía el estado de Nyx a la interfaz.

Seguridad: solo escucha en 127.0.0.1, solo acepta los orígenes de la webview de Tauri
y exige el token de la sesión en el primer mensaje. Sin esto, cualquier web abierta
en el navegador podría conectarse a ws://127.0.0.1.
"""

from __future__ import annotations

import asyncio
import hmac
import logging
from collections.abc import Sequence

from pydantic import ValidationError
from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.exceptions import ConnectionClosed
from websockets.typing import Origin

from nyx import __version__
from nyx.bridge.protocol import (
    PROTOCOL_VERSION,
    ActionButton,
    ActionMsg,
    BubbleHideMsg,
    BubbleMsg,
    GameMsg,
    Hello,
    LevelMsg,
    StateMsg,
    TalkKeyMsg,
    TextInput,
    Welcome,
    _Msg,
    client_adapter,
)
from nyx.bus import EventBus
from nyx.events import (
    ActionChosen,
    AudioLevel,
    BubbleHidden,
    BubbleShown,
    NyxState,
    StateChanged,
    TalkKey,
    TextEntered,
)
from nyx.game.detector import GameStateChanged

log = logging.getLogger(__name__)

# Orígenes de la webview de Tauri 2 en Windows (producción) y del servidor de Vite (desarrollo).
DEFAULT_ORIGINS: tuple[str, ...] = (
    "http://tauri.localhost",
    "https://tauri.localhost",
    "http://localhost:1420",
)
AUTH_TIMEOUT_S = 3.0
CLOSE_UNAUTHORIZED = 4401
CLOSE_BAD_PROTOCOL = 4400


class UIBridge:
    def __init__(
        self,
        bus: EventBus,
        token: str,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        origins: Sequence[str] = DEFAULT_ORIGINS,
        indicator_size: int = 100,
    ) -> None:
        self.indicator_size = indicator_size
        self._game: GameMsg | None = None
        self._bus = bus
        self._token = token
        self._host = host
        self._port = port
        self._origins = [Origin(o) for o in origins]
        self._server: Server | None = None
        self._clients: set[ServerConnection] = set()
        self._state = NyxState.IDLE
        self._unsubscribe = [
            bus.subscribe(StateChanged, self._on_state),
            bus.subscribe(AudioLevel, self._on_level),
            bus.subscribe(BubbleShown, self._on_bubble),
            bus.subscribe(BubbleHidden, self._on_bubble_hidden),
            bus.subscribe(GameStateChanged, self._on_game),
        ]

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def start(self) -> int:
        """Arranca el servidor y devuelve el puerto real (útil con port=0)."""
        self._server = await serve(
            self._handle,
            self._host,
            self._port,
            origins=self._origins,
            max_size=64 * 1024,
        )
        port: int = self._server.sockets[0].getsockname()[1]
        log.info("UIBridge escuchando en %s:%d", self._host, port)
        return port

    async def stop(self) -> None:
        for unsubscribe in self._unsubscribe:
            unsubscribe()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, conn: ServerConnection) -> None:
        if not await self._authenticate(conn):
            return
        self._clients.add(conn)
        log.info("Interfaz conectada (%d)", len(self._clients))
        try:
            await conn.send(
                Welcome(version=__version__, indicator_size=self.indicator_size).model_dump_json()
            )
            await conn.send(StateMsg(state=self._state).model_dump_json())
            if self._game is not None:  # una ventana que se abre a mitad de partida
                await conn.send(self._game.model_dump_json())
            async for raw in conn:
                await self._dispatch(raw)
        except ConnectionClosed:
            pass
        finally:
            self._clients.discard(conn)
            log.info("Interfaz desconectada (%d)", len(self._clients))

    async def _authenticate(self, conn: ServerConnection) -> bool:
        try:
            raw = await asyncio.wait_for(conn.recv(), AUTH_TIMEOUT_S)
            hello = client_adapter.validate_json(raw)
        except (TimeoutError, ValidationError, ConnectionClosed):
            await conn.close(CLOSE_UNAUTHORIZED, "hello requerido")
            return False
        if not isinstance(hello, Hello) or not hmac.compare_digest(
            hello.token.encode(), self._token.encode()
        ):
            log.warning("Conexión rechazada: token no válido")
            await conn.close(CLOSE_UNAUTHORIZED, "token no válido")
            return False
        if hello.protocol != PROTOCOL_VERSION:
            await conn.close(CLOSE_BAD_PROTOCOL, f"protocolo {PROTOCOL_VERSION} requerido")
            return False
        return True

    async def _dispatch(self, raw: str | bytes) -> None:
        try:
            msg = client_adapter.validate_json(raw)
        except ValidationError:
            log.warning("Mensaje de la interfaz no válido")
            return
        if isinstance(msg, TextInput):
            await self._bus.publish(TextEntered(msg.text.strip()))
        elif isinstance(msg, TalkKeyMsg):
            await self._bus.publish(TalkKey(msg.pressed))
        elif isinstance(msg, ActionMsg):
            await self._bus.publish(ActionChosen(msg.id))

    async def broadcast(self, msg: _Msg) -> None:
        if not self._clients:
            return
        data = msg.model_dump_json()
        for conn in list(self._clients):
            try:
                await conn.send(data)
            except ConnectionClosed:
                self._clients.discard(conn)

    async def _on_state(self, event: StateChanged) -> None:
        self._state = event.state
        await self.broadcast(StateMsg(state=event.state))

    async def _on_level(self, event: AudioLevel) -> None:
        await self.broadcast(LevelMsg(rms=min(max(event.rms, 0.0), 1.0)))

    async def _on_bubble(self, event: BubbleShown) -> None:
        actions = [ActionButton(id=a.id, label=a.label, primary=a.primary) for a in event.actions]
        await self.broadcast(
            BubbleMsg(
                display=event.display,
                secondary=event.secondary,
                actions=actions,
                alert=event.alert,
            )
        )

    async def _on_bubble_hidden(self, _: BubbleHidden) -> None:
        await self.broadcast(BubbleHideMsg())

    async def _on_game(self, event: GameStateChanged) -> None:
        mode = event.mode if event.mode in ("off", "voice", "normal") else "voice"
        self._game = GameMsg(active=event.active, mode=mode)  # type: ignore[arg-type]
        await self.broadcast(self._game)
