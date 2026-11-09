import asyncio
import json
from collections.abc import AsyncIterator

import pytest
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from nyx.bridge.protocol import PROTOCOL_VERSION, server_adapter
from nyx.bridge.server import CLOSE_UNAUTHORIZED, UIBridge
from nyx.bus import EventBus
from nyx.events import (
    ActionChosen,
    AudioLevel,
    BubbleShown,
    NyxState,
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
        }


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
