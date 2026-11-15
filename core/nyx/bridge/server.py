"""UIBridge: servidor WebSocket local que envía el estado de Nyx a la interfaz.

Seguridad: solo escucha en 127.0.0.1, solo acepta los orígenes de la webview de Tauri
y exige el token de la sesión en el primer mensaje. Sin esto, cualquier web abierta
en el navegador podría conectarse a ws://127.0.0.1.
"""

from __future__ import annotations

import asyncio
import hmac
import logging
from collections.abc import Mapping, Sequence

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
    ExtensionsMsg,
    ExtMsg,
    GameMsg,
    GlassInfo,
    Hello,
    LevelMsg,
    LongSectionMsg,
    MicLevelMsg,
    NyxReadyMsg,
    OpenSettingsMsg,
    PanelNoteMsg,
    ReadingMsg,
    SettingsGetMsg,
    SettingsMsg,
    SettingsSetMsg,
    SetupFlowMsg,
    SetupFlowStateMsg,
    SetupMsg,
    SetupProgressMsg,
    SetupResultMsg,
    SetupStatusMsg,
    StateMsg,
    TalkKeyMsg,
    TextInput,
    ToolInfo,
    UpdateApplyMsg,
    UpdateMsg,
    VoiceInfo,
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
    ExtRequested,
    ExtStatusChanged,
    MicLevelChanged,
    NyxReady,
    NyxState,
    OpenSettingsWindow,
    PanelNote,
    ReadingAppended,
    SettingsChanged,
    SettingsRequested,
    SetupFlowChanged,
    SetupFlowRequested,
    SetupProgress,
    SetupRequested,
    SetupResult,
    SetupStatusChanged,
    StateChanged,
    TalkKey,
    TextEntered,
    UpdateApply,
    UpdateOffered,
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
        glass: GlassInfo | None = None,
        tools: Sequence[ToolInfo] = (),
        voices: Sequence[VoiceInfo] = (),
        look: Mapping[str, str] | None = None,
        onboarding_done: bool = True,
    ) -> None:
        self.indicator_size = indicator_size
        self.glass = glass or GlassInfo()
        self.tools = list(tools)
        self.voices = list(voices)
        self.onboarding_done = onboarding_done
        # v10: fuente, color de Nyx y tinte de los paneles (Ajustes → Apariencia).
        self.look = {
            "font": "segoe",
            "nyx_color": "blanco",
            "panel_tint": "gris",
            "ready_indicator": "onda",
            **(look or {}),
        }
        self._game: GameMsg | None = None
        self._setup_flow: SetupFlowStateMsg | None = None
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
            bus.subscribe(ReadingAppended, self._on_reading),
            bus.subscribe(PanelNote, self._on_panel_note),
            bus.subscribe(GameStateChanged, self._on_game),
            bus.subscribe(SettingsChanged, self._on_settings),
            bus.subscribe(OpenSettingsWindow, self._on_open_settings),
            bus.subscribe(SetupStatusChanged, self._on_setup_status),
            bus.subscribe(ExtStatusChanged, self._on_ext_status),
            bus.subscribe(SetupProgress, self._on_setup_progress),
            bus.subscribe(MicLevelChanged, self._on_mic_level),
            bus.subscribe(SetupResult, self._on_setup_result),
            bus.subscribe(SetupFlowChanged, self._on_setup_flow),
            bus.subscribe(NyxReady, self._on_ready),
            bus.subscribe(UpdateApply, self._on_update_apply),
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
                Welcome(
                    version=__version__,
                    indicator_size=self.indicator_size,
                    glass=self.glass,
                    font=self.look["font"],
                    nyx_color=self.look["nyx_color"],
                    panel_tint=self.look["panel_tint"],
                    ready_indicator=self.look["ready_indicator"],
                    onboarding_done=self.onboarding_done,
                ).model_dump_json()
            )
            await conn.send(StateMsg(state=self._state).model_dump_json())
            if self._game is not None:  # una ventana que se abre a mitad de partida
                await conn.send(self._game.model_dump_json())
            if self._setup_flow is not None:  # el panel del primer arranque, si va por la mitad
                await conn.send(self._setup_flow.model_dump_json())
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
        except TimeoutError, ValidationError, ConnectionClosed:
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
        elif isinstance(msg, SettingsGetMsg):
            await self._bus.publish(SettingsRequested())
        elif isinstance(msg, SettingsSetMsg):
            await self._bus.publish(SettingsRequested(dict(msg.patch)))
        elif isinstance(msg, SetupMsg):
            await self._bus.publish(SetupRequested(msg.action, msg.arg))
        elif isinstance(msg, SetupFlowMsg):
            await self._bus.publish(SetupFlowRequested(msg.action, msg.value))
        elif isinstance(msg, ExtMsg):
            await self._bus.publish(ExtRequested(msg.action, msg.id, msg.path, msg.key, msg.value))
        elif isinstance(msg, UpdateMsg):
            await self._bus.publish(UpdateOffered(msg.version))

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
                kind=event.kind,
                expires_s=event.expires_s,
                text=event.text,
                sections=[
                    LongSectionMsg(title=s.title, items=list(s.items), ordered=s.ordered)
                    for s in event.sections
                ],
                reading=event.reading,
            )
        )

    async def _on_reading(self, event: ReadingAppended) -> None:
        await self.broadcast(ReadingMsg(text=event.text, duration_s=max(0.0, event.duration_s)))

    async def _on_panel_note(self, event: PanelNote) -> None:
        await self.broadcast(PanelNoteMsg(text=event.text, undo_action=event.undo_action))

    async def _on_open_settings(self, event: OpenSettingsWindow) -> None:
        # Una sección desconocida abre la primera (lo valida el propio mensaje).
        try:
            msg = OpenSettingsMsg.model_validate({"section": event.section})
        except ValidationError:
            msg = OpenSettingsMsg()
        await self.broadcast(msg)

    async def _on_ext_status(self, event: ExtStatusChanged) -> None:
        await self.broadcast(
            ExtensionsMsg(
                items=event.items,
                dev_mode=event.dev_mode,
                inspect=event.inspect,
                error=event.error,
                official=event.official,
            )
        )

    async def _on_setup_status(self, event: SetupStatusChanged) -> None:
        await self.broadcast(SetupStatusMsg(status=event.status))

    async def _on_setup_progress(self, event: SetupProgress) -> None:
        await self.broadcast(
            SetupProgressMsg(
                key=event.key,
                label=event.label,
                done_mb=event.done_mb,
                total_mb=event.total_mb,
                finished=event.finished,
                error=event.error,
            )
        )

    async def _on_mic_level(self, event: MicLevelChanged) -> None:
        await self.broadcast(MicLevelMsg(rms=min(max(event.rms, 0.0), 1.0)))

    async def _on_setup_result(self, event: SetupResult) -> None:
        await self.broadcast(
            SetupResultMsg(action=event.action, ok=event.ok, message=event.message)
        )

    async def _on_update_apply(self, event: UpdateApply) -> None:
        await self.broadcast(UpdateApplyMsg(version=event.version))

    async def _on_ready(self, _: NyxReady) -> None:
        await self.broadcast(NyxReadyMsg())

    async def _on_setup_flow(self, event: SetupFlowChanged) -> None:
        self._setup_flow = SetupFlowStateMsg(state=event.state)
        await self.broadcast(self._setup_flow)

    async def _on_settings(self, event: SettingsChanged) -> None:
        # Las ventanas que se abran después reciben ya los valores nuevos en «welcome».
        appearance = event.data.get("appearance", {})
        if isinstance(appearance, dict):
            self.indicator_size = int(appearance.get("indicator_size", self.indicator_size))
            glass = appearance.get("glass")
            if isinstance(glass, dict):
                self.glass = GlassInfo.model_validate(glass)
            for key in self.look:
                if isinstance(appearance.get(key), str):
                    self.look[key] = appearance[key]
        onboarding = event.data.get("onboarding", {})
        if isinstance(onboarding, dict) and isinstance(onboarding.get("done"), bool):
            self.onboarding_done = onboarding["done"]
        await self.broadcast(
            SettingsMsg(
                data=event.data,
                restart=list(event.restart),
                error=event.error,
                tools=self.tools,
                inputs=list(event.inputs),
                outputs=list(event.outputs),
                voices=self.voices,
            )
        )

    async def _on_bubble_hidden(self, _: BubbleHidden) -> None:
        await self.broadcast(BubbleHideMsg())

    async def _on_game(self, event: GameStateChanged) -> None:
        mode = event.mode if event.mode in ("off", "voice", "normal") else "voice"
        self._game = GameMsg(
            active=event.active,
            mode=mode,  # type: ignore[arg-type]
            monitor=event.monitor,
        )
        await self.broadcast(self._game)
