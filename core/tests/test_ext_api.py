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


async def test_settings_only_its_own(monkeypatch: pytest.MonkeyPatch) -> None:
    """7.14: lee sus ajustes sin permiso, solo los de su manifiesto, y con `secrets.set` no
    puede cambiarlos (van aparte)."""
    store: dict[str, str] = {}
    monkeypatch.setattr(api_module, "_cred_write", lambda t, v: store.__setitem__(t, v))
    monkeypatch.setattr(api_module, "_cred_read", store.get)
    monkeypatch.setattr(api_module, "_cred_delete", lambda t: store.pop(t, None))
    api = ExtensionApi(EventBus(), lambda _id: ("secrets",), settings_of=lambda _id: ("password",))
    api_module.write_setting("x.y", "password", "1234")
    assert await api.setting_get("x.y", {"key": "password"}) == "1234"
    with pytest.raises(RpcError, match="manifiesto"):
        await api.setting_get("x.y", {"key": "otra"})
    await api.secret_set("x.y", {"key": "password", "value": "trampa"})
    assert await api.setting_get("x.y", {"key": "password"}) == "1234"
    api_module.write_setting("x.y", "password", "")
    assert await api.setting_get("x.y", {"key": "password"}) is None


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


# --- Iniciar sesión (OAuth con PKCE) y abrir su app (7.14) -------------------------------------

SPOTIFY = ("net:accounts.spotify.com:443", "apps:launch")


def browser(*, accept: bool = True, state: str | None = None) -> Any:
    """Hace de navegador: el usuario entra y el servicio vuelve a la dirección de Nyx."""
    from urllib.parse import parse_qs, urlencode, urlsplit

    seen: list[dict[str, str]] = []

    def open_url(url: str) -> None:
        query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        seen.append(query)
        back = {"state": state or query["state"]}
        back |= {"code": "codigo"} if accept else {"error": "access_denied"}
        httpx.get(f"{query['redirect_uri']}?{urlencode(back)}", timeout=5)

    open_url.seen = seen  # type: ignore[attr-defined]
    return open_url


async def test_oauth_with_pkce() -> None:
    import base64
    import hashlib
    from urllib.parse import parse_qs

    sent: list[dict[str, str]] = []

    def token_server(request: httpx.Request) -> httpx.Response:
        sent.append({k: v[0] for k, v in parse_qs(request.content.decode()).items()})
        return httpx.Response(200, json={"access_token": "a", "refresh_token": "r", "x": 1})

    open_url = browser()
    api = ExtensionApi(
        EventBus(),
        lambda _id: SPOTIFY,
        open_url=open_url,
        transport=httpx.MockTransport(token_server),
    )
    tokens = await api.oauth_authorize(
        "tepnyx.spotify",
        {
            "authorize_url": "https://accounts.spotify.com/authorize",
            "token_url": "https://accounts.spotify.com/api/token",
            "client_id": "mi-app",
            "scopes": "user-modify-playback-state",
        },
    )
    assert tokens == {"access_token": "a", "refresh_token": "r"}  # solo lo que hace falta
    (asked,) = open_url.seen
    assert asked["redirect_uri"].startswith("http://127.0.0.1:")
    assert asked["code_challenge_method"] == "S256"
    (form,) = sent
    assert form["code"] == "codigo" and form["redirect_uri"] == asked["redirect_uri"]
    digest = hashlib.sha256(form["code_verifier"].encode()).digest()
    assert base64.urlsafe_b64encode(digest).decode().rstrip("=") == asked["code_challenge"]


@pytest.mark.parametrize(
    ("params", "playing", "error"),
    [
        ({"authorize_url": "https://otro.com/authorize"}, False, "sin permiso"),
        ({"authorize_url": "http://accounts.spotify.com/authorize"}, False, "no válida"),
        ({"client_id": ""}, False, "client_id"),
        ({}, True, "partida"),
    ],
)
async def test_oauth_refused(params: dict[str, str], playing: bool, error: str) -> None:
    api = ExtensionApi(EventBus(), lambda _id: SPOTIFY, open_url=browser(), playing=lambda: playing)
    base = {
        "authorize_url": "https://accounts.spotify.com/authorize",
        "token_url": "https://accounts.spotify.com/api/token",
        "client_id": "mi-app",
    }
    with pytest.raises(RpcError, match=error):
        await api.oauth_authorize("x.y", base | params)


async def test_oauth_cancelled_or_forged() -> None:
    base = {
        "authorize_url": "https://accounts.spotify.com/authorize",
        "token_url": "https://accounts.spotify.com/api/token",
        "client_id": "mi-app",
        "timeout_s": 1,
    }
    denied = ExtensionApi(EventBus(), lambda _id: SPOTIFY, open_url=browser(accept=False))
    with pytest.raises(RpcError, match="access_denied"):
        await denied.oauth_authorize("x.y", base)
    # Otra web que llama a la dirección de Nyx sin el «state» bueno: no vale.
    forged = ExtensionApi(EventBus(), lambda _id: SPOTIFY, open_url=browser(state="otro"))
    with pytest.raises(RpcError, match="a tiempo"):
        await forged.oauth_authorize("x.y", base)


async def test_open_uri_only_its_app_and_webs() -> None:
    opened: list[str] = []
    api = ExtensionApi(EventBus(), lambda _id: SPOTIFY, open_url=opened.append)
    await api.open_uri("x.y", {"uri": "spotify:search:queen"})
    await api.open_uri("x.y", {"uri": "https://accounts.spotify.com/"})
    assert opened == ["spotify:search:queen", "https://accounts.spotify.com/"]
    for uri in ("file:///C:/Windows/notepad.exe", "ms-settings:", "https://otra.com/", "calc"):
        with pytest.raises(RpcError):
            await api.open_uri("x.y", {"uri": uri})
    plain = ExtensionApi(EventBus(), lambda _id: (), open_url=opened.append)
    with pytest.raises(RpcError, match="sin permiso"):
        await plain.open_uri("x.y", {"uri": "spotify:"})
