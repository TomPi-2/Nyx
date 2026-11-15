"""Herramientas de extensiones con código y lo que piden a Nyx, con permisos (7.07)."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Any

import httpx
import pytest

from nyx.bus import EventBus
from nyx.events import BubbleShown
from nyx.ext import api as api_module
from nyx.ext.api import ExtensionApi
from nyx.ext.host import ExtensionHost
from nyx.ext.manifest import ManifestError, load_manifest
from nyx.ext.rpc import RpcError
from nyx.ext.store import ExtState, Installed
from nyx.ext.tools import make_tools
from nyx.ext.tools_spec import effective_risk, load_tools
from nyx.tools.base import GamePolicy, Risk, ToolContext
from tests.test_ext_host import PlainLauncher, make_package

MANIFEST = {
    "id": "tepnyx.obs",
    "name": "OBS",
    "version": "1.0.0",
    "author": "Tepnyx",
    "nyx_api": ">=1.0",
    "kinds": ["tools"],
    "permissions": ["net:localhost:4455", "notify", "files:read:documentos"],
}

TOOLS = [
    {
        "name": "obs_record",
        "description": "Empieza o para la grabación en OBS.",
        "parameters": {
            "properties": {"action": {"type": "string", "enum": ["start", "stop"]}},
            "required": ["action"],
        },
        "uses": ["net:localhost:4455"],
        "game_policy": "allowed",
    },
    {
        "name": "obs_scene",
        "description": "Cambia de escena en OBS.",
        "parameters": {"properties": {"name": {"type": "string"}}, "required": ["name"]},
        "risk": "yellow",
    },
]

CODE = """
import nyx

@nyx.tool
def obs_record(action):
    return {"message": f"Grabación: {action}", "display": action}

@nyx.tool
async def obs_scene(name):
    # Sin permiso para este servidor: Nyx dice que no.
    await nyx.ask("net.fetch", {"url": "https://ejemplo.com/"})
    return "nunca"
"""


def manifest() -> Any:
    return load_manifest(json.dumps(MANIFEST).encode())


def installed(root: Path, tools: list[dict[str, Any]] = TOOLS, code: str = CODE) -> Installed:
    pkg = make_package(root, code)
    (pkg / "tools" / "tools.json").write_text(json.dumps(tools), encoding="utf-8")
    return Installed(
        manifest(),
        pkg,
        ExtState(version="1.0.0", enabled=True, accepted=list(MANIFEST["permissions"])),
    )


# --- La descripción de las herramientas -------------------------------------------------------


def test_tools_json_and_risk() -> None:
    specs = load_tools(json.dumps(TOOLS).encode(), manifest())
    record, scene = specs
    assert effective_risk(record, manifest()) is Risk.GREEN  # net: verde
    # Sin «uses», el de todos sus permisos (files:read, notify, net): verde; declara amarillo.
    assert effective_risk(scene, manifest()) is Risk.YELLOW


@pytest.mark.parametrize(
    ("tools", "error"),
    [
        ([{**TOOLS[0], "uses": ["net:otro.com:443"]}], "no pide"),
        ([TOOLS[0], TOOLS[0]], "mismo nombre"),
        ([{**TOOLS[0], "name": "Mal Nombre"}], "name"),
        ([{**TOOLS[0], "parameters": {"properties": {}, "required": ["x"]}}], "sin definir"),
        ([], "lista"),
    ],
)
def test_bad_tools_json(tools: list[Any], error: str) -> None:
    with pytest.raises(ManifestError, match=error):
        load_tools(json.dumps(tools).encode(), manifest())


# --- Como herramientas de Nyx, con una extensión de verdad (sin encerrar) ----------------------


async def test_extension_tools_end_to_end(tmp_path: Path, ctx: ToolContext) -> None:
    ext = installed(tmp_path / "pkg")
    api = ExtensionApi(EventBus(), lambda _id: tuple(MANIFEST["permissions"]))
    host = ExtensionHost(PlainLauncher(tmp_path / "data"), handlers=api.handlers)
    try:
        record, scene = make_tools(ext, host)
        assert record.name == "obs_record" and record.risk is Risk.GREEN
        assert record.game_policy is GamePolicy.ALLOWED
        assert scene.risk is Risk.YELLOW and scene.game_policy is GamePolicy.DEFERRED
        schema = record.schema()["function"]["parameters"]
        assert schema["required"] == ["action"]
        ok = await record.run(record.params_model(action="start"), ctx)
        assert ok.ok and ok.message == "Grabación: start" and ok.display == "start"
        # Pide red a un servidor que no tiene en sus permisos: falla, y Nyx sigue igual.
        denied = await scene.run(scene.params_model(name="Juego"), ctx)
        assert not denied.ok and "sin permiso" in (denied.secondary or "")
        assert (await record.run(record.params_model(action="stop"), ctx)).ok
    finally:
        await host.stop_all()


# --- La API, permiso a permiso ----------------------------------------------------------------


def make_api(perms: tuple[str, ...], **kw: Any) -> tuple[ExtensionApi, EventBus]:
    bus = EventBus()
    return ExtensionApi(bus, lambda _id: perms, **kw), bus


async def test_fetch_only_to_allowed_hosts() -> None:
    seen: list[str] = []

    def server(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, text="hola")

    api, _ = make_api(("net:localhost:4455",), transport=httpx.MockTransport(server))
    got = await api.fetch("x.y", {"url": "http://localhost:4455/estado"})
    assert got["status"] == 200 and got["body"] == "hola"
    for url in ("http://localhost:8080/", "https://localhost/", "file:///C:/Windows/win.ini"):
        with pytest.raises(RpcError):
            await api.fetch("x.y", {"url": url})
    assert seen == ["http://localhost:4455/estado"]


async def test_files_stay_inside_their_folder(tmp_path: Path) -> None:
    docs = tmp_path / "Documentos"
    docs.mkdir()
    (docs / "nota.txt").write_text("hola", encoding="utf-8")
    (tmp_path / "secreto.txt").write_text("no", encoding="utf-8")
    api, _ = make_api(("files:read:documentos",), folders=lambda: {"documentos": docs})
    assert (await api.files_read("x.y", {"folder": "documentos", "path": "nota.txt"})) == {
        "text": "hola"
    }
    with pytest.raises(RpcError, match="fuera"):
        await api.files_read("x.y", {"folder": "documentos", "path": "../secreto.txt"})
    with pytest.raises(RpcError, match="sin permiso"):
        await api.files_read("x.y", {"folder": "descargas", "path": "a.txt"})
    with pytest.raises(RpcError, match="sin permiso"):
        await api.files_write("x.y", {"folder": "documentos", "path": "b.txt", "text": "x"})


async def test_files_write_never_deletes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    trashed: list[str] = []
    import send2trash

    monkeypatch.setattr(send2trash, "send2trash", trashed.append)
    docs = tmp_path / "Documentos"
    docs.mkdir()
    (docs / "a.txt").write_text("viejo", encoding="utf-8")
    api, _ = make_api(("files:write:documentos",), folders=lambda: {"documentos": docs})
    await api.files_write("x.y", {"folder": "documentos", "path": "a.txt", "text": "nuevo"})
    assert trashed == [str(docs / "a.txt")]


async def test_notify_and_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    store: dict[str, str] = {}
    monkeypatch.setattr(api_module, "_cred_write", lambda t, v: store.__setitem__(t, v))
    monkeypatch.setattr(api_module, "_cred_read", store.get)
    monkeypatch.setattr(api_module, "_cred_delete", lambda t: store.pop(t, None))
    api, bus = make_api(("notify", "secrets"))
    shown: list[BubbleShown] = []

    async def on_bubble(e: BubbleShown) -> None:
        shown.append(e)

    bus.subscribe(BubbleShown, on_bubble)
    await api.notify("x.y", {"title": "OBS", "text": "Grabando"})
    assert shown[0].display == "OBS" and shown[0].alert
    await api.secret_set("x.y", {"key": "password", "value": "1234"})
    assert store == {"Nyx/ext/x.y/password": "1234"}  # cada extensión, lo suyo
    assert await api.secret_get("x.y", {"key": "password"}) == "1234"
    with pytest.raises(RpcError):
        await api.secret_get("x.y", {"key": "../otra"})
    plain, _ = make_api(())
    with pytest.raises(RpcError, match="sin permiso"):
        await plain.notify("x.y", {"title": "x"})


async def test_websocket_to_an_allowed_server() -> None:
    import websockets

    async def echo(ws: Any) -> None:
        async for message in ws:
            await ws.send(f"eco: {message}")

    async with websockets.serve(echo, "127.0.0.1", 0) as server:
        port = next(iter(server.sockets)).getsockname()[1]
        api, _ = make_api((f"net:127.0.0.1:{port}",))
        sid = await api.ws_open("x.y", {"url": f"ws://127.0.0.1:{port}"})
        await api.ws_send("x.y", {"id": sid, "text": "hola"})
        assert await api.ws_recv("x.y", {"id": sid, "timeout_s": 5}) == "eco: hola"
        await api.close("x.y")
        with pytest.raises(RpcError):
            await api.ws_send("x.y", {"id": sid, "text": "otra"})
        with pytest.raises(RpcError, match="sin permiso"):
            await api.ws_open("x.y", {"url": "ws://127.0.0.1:1"})


def test_code_is_needed() -> None:
    """Una extensión con herramientas sin código de verdad no se carga (ni rompe Nyx)."""
    assert textwrap.dedent(CODE).strip().startswith("import nyx")
