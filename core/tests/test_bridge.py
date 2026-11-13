import asyncio
import json
from collections.abc import AsyncIterator

import pytest
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from nyx.bridge.protocol import PROTOCOL_VERSION, GlassInfo, server_adapter
from nyx.bridge.server import CLOSE_UNAUTHORIZED, UIBridge
from nyx.bus import EventBus
from nyx.events import (
    ActionChosen,
    AudioLevel,
    BubbleAction,
    BubbleShown,
    LongSection,
    NyxState,
    PanelNote,
    ReadingAppended,
    SettingsChanged,
    SettingsRequested,
    StateChanged,
    TalkKey,
    TextEntered,
)

TOKEN = "secreto-de-prueba"
ORIGIN = "http://localhost:1420"


@pytest.fixture
async def bridge() -> AsyncIterator[tuple[EventBus, int]]:
    bus = EventBus()
    b = UIBridge(bus, TOKEN)
    port = await b.start()
    yield bus, port
    await b.stop()


async def _hello(conn: ClientConnection, token: str = TOKEN) -> None:
    await conn.send(json.dumps({"type": "hello", "token": token, "protocol": PROTOCOL_VERSION}))


async def _recv(conn: ClientConnection) -> dict[str, object]:
    data = json.loads(await conn.recv())
    server_adapter.validate_python(data)  # el núcleo solo envía mensajes válidos
    assert isinstance(data, dict)
    return data


async def test_handshake_and_events(bridge: tuple[EventBus, int]) -> None:
    bus, port = bridge
    async with connect(f"ws://127.0.0.1:{port}", origin=ORIGIN) as conn:  # type: ignore[arg-type]
        await _hello(conn)
        assert (await _recv(conn))["type"] == "welcome"
        assert await _recv(conn) == {"type": "state", "state": "idle"}

        await bus.publish(StateChanged(NyxState.LISTENING))
        assert await _recv(conn) == {"type": "state", "state": "listening"}
        await bus.publish(AudioLevel(rms=1.7))
        assert await _recv(conn) == {"type": "level", "rms": 1.0}
        await bus.publish(BubbleShown(display="Hallo", secondary="hola · alemán"))
        assert await _recv(conn) == {
            "type": "bubble",
            "display": "Hallo",
            "secondary": "hola · alemán",
            "actions": [],
            "alert": False,
            "kind": "response",
            "expires_s": None,
            "text": "",
            "sections": [],
            "reading": False,
        }
        # v17 (6.28): panel largo, frases al ritmo de la voz y aviso al pie.
        await bus.publish(
            BubbleShown(
                display="Tortilla",
                kind="long",
                sections=(LongSection("Pasos", ("Batir", "Cuajar"), ordered=True),),
            )
        )
        long = await _recv(conn)
        assert long["kind"] == "long"
        assert long["sections"] == [
            {"title": "Pasos", "items": ["Batir", "Cuajar"], "ordered": True}
        ]
        await bus.publish(ReadingAppended("Hola.", 1.5))
        assert await _recv(conn) == {"type": "reading", "text": "Hola.", "duration_s": 1.5}
        await bus.publish(PanelNote("Copiado"))
        assert await _recv(conn) == {"type": "panel_note", "text": "Copiado", "undo_action": None}


async def test_wrong_token_is_rejected(bridge: tuple[EventBus, int]) -> None:
    _, port = bridge
    async with connect(f"ws://127.0.0.1:{port}", origin=ORIGIN) as conn:  # type: ignore[arg-type]
        await _hello(conn, token="otro")
        with pytest.raises(ConnectionClosed) as exc:
            await conn.recv()
        assert exc.value.rcvd is not None
        assert exc.value.rcvd.code == CLOSE_UNAUTHORIZED


async def test_foreign_origin_is_rejected(bridge: tuple[EventBus, int]) -> None:
    _, port = bridge
    with pytest.raises(InvalidStatus):
        async with connect(f"ws://127.0.0.1:{port}", origin="https://evil.example"):  # type: ignore[arg-type]
            pass


async def test_client_messages_are_published(bridge: tuple[EventBus, int]) -> None:
    bus, port = bridge
    got: list[object] = []

    async def collect(event: object) -> None:
        got.append(event)

    bus.subscribe(TextEntered, collect)
    bus.subscribe(TalkKey, collect)
    bus.subscribe(ActionChosen, collect)
    async with connect(f"ws://127.0.0.1:{port}", origin=ORIGIN) as conn:  # type: ignore[arg-type]
        await _hello(conn)
        await _recv(conn)
        await _recv(conn)
        await conn.send(json.dumps({"type": "text", "text": "  hola  "}))
        await conn.send(json.dumps({"type": "talk", "pressed": True}))
        await conn.send(json.dumps({"type": "text", "text": ""}))  # no válido: se ignora
        await conn.send(json.dumps({"type": "talk", "pressed": False}))
        await conn.send(json.dumps({"type": "action", "id": "confirm-1"}))
        for _ in range(50):
            if len(got) == 4:
                break
            await asyncio.sleep(0.01)
    assert got == [TextEntered("hola"), TalkKey(True), TalkKey(False), ActionChosen("confirm-1")]


async def test_welcome_carries_glass_settings() -> None:
    """v7: cada ventana recibe los ajustes del cristal al conectarse."""
    bus = EventBus()
    glass = GlassInfo(quality="medio", motion="interaccion", edge=7, show_in_captures=True)
    b = UIBridge(bus, TOKEN, glass=glass)
    port = await b.start()
    try:
        async with connect(f"ws://127.0.0.1:{port}", origin=ORIGIN) as conn:  # type: ignore[arg-type]
            await _hello(conn)
            welcome = await _recv(conn)
            assert welcome["glass"] == {
                "quality": "medio",
                "motion": "interaccion",
                "edge": 7,
                "show_in_captures": True,
            }
    finally:
        await b.stop()


async def test_bubble_kind_and_expiry(bridge: tuple[EventBus, int]) -> None:
    """v7: la confirmación y el deshacer dicen qué panel son y cuánto duran."""
    bus, port = bridge
    async with connect(f"ws://127.0.0.1:{port}", origin=ORIGIN) as conn:  # type: ignore[arg-type]
        await _hello(conn)
        await _recv(conn)
        await _recv(conn)
        await bus.publish(
            BubbleShown(
                display="¿Muevo 3 archivos a la papelera?",
                actions=(BubbleAction("yes-1", "Confirmar", primary=True),),
                kind="confirm",
                expires_s=15.0,
            )
        )
        msg = await _recv(conn)
        assert (msg["kind"], msg["expires_s"]) == ("confirm", 15.0)


async def test_settings_roundtrip(bridge: tuple[EventBus, int]) -> None:
    """v8: Ajustes pide y cambia ajustes; la respuesta llega a todas las ventanas."""
    bus, port = bridge
    requests: list[SettingsRequested] = []

    async def answer(event: SettingsRequested) -> None:
        requests.append(event)
        data = {"appearance": {"indicator_size": 120, "glass": {"edge": 8}}}
        await bus.publish(SettingsChanged(data=data, restart=("llm.model",)))

    bus.subscribe(SettingsRequested, answer)
    async with connect(f"ws://127.0.0.1:{port}", origin=ORIGIN) as conn:  # type: ignore[arg-type]
        await _hello(conn)
        await _recv(conn)
        await _recv(conn)
        await conn.send(json.dumps({"type": "settings_set", "patch": {"game": {"mode": "off"}}}))
        msg = await _recv(conn)
        assert msg["type"] == "settings"
        assert msg["restart"] == ["llm.model"]
    assert requests == [SettingsRequested({"game": {"mode": "off"}})]
