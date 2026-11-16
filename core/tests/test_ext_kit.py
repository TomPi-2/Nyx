"""El kit de extensiones (7.12): plantillas de `nyx_ext.py` y el Nyx falso del SDK (sdk/)."""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sdk" / "src"))
sys.path.insert(0, str(ROOT / "core" / "scripts"))

import nyx_ext  # noqa: E402
from nyx_sdk.testing import FakeNyx, PermissionDeniedError  # noqa: E402

import nyx  # noqa: E402  (el de verdad: el Nyx falso no puede pisarlo)


@pytest.mark.parametrize("kind", sorted(nyx_ext.EXAMPLES))
def test_every_template_validates_and_packs(tmp_path: Path, kind: str) -> None:
    folder = tmp_path / kind
    nyx_ext.new(folder, f"prueba.{kind}", kind)
    assert nyx_ext.validate(folder)
    out = tmp_path / f"{kind}.nyxext"
    nyx_ext.pack(folder, out)
    names = zipfile.ZipFile(out).namelist()
    assert "manifest.json" in names
    assert not any(n.startswith("tests/") for n in names)  # las pruebas no van en el paquete


def test_new_never_overwrites(tmp_path: Path) -> None:
    (tmp_path / "x.txt").write_text("mío", encoding="utf-8")
    with pytest.raises(SystemExit):
        nyx_ext.new(tmp_path, "prueba.algo", "tools")
    assert (tmp_path / "x.txt").read_text(encoding="utf-8") == "mío"


def test_validate_catches_a_tool_without_code(tmp_path: Path) -> None:
    folder = tmp_path / "e"
    nyx_ext.new(folder, "prueba.algo", "tools")
    (folder / "tools" / "main.py").unlink()
    assert not nyx_ext.validate(folder)


# --- El Nyx falso -------------------------------------------------------------------------------

MAIN = """
import nyx

@nyx.tool
async def escena(nombre: str, rapido: bool = False) -> dict:
    sock = await nyx.ask("ws.open", {"url": "ws://localhost:4455"})
    await nyx.ask("ws.send", {"id": sock, "text": nombre})
    return {"escena": nombre, "rapido": rapido, "sock": sock}

@nyx.tool
def clave() -> str:
    return nyx.ask_sync("secrets.get", {"key": "password"})

@nyx.tool
async def fuera() -> None:
    await nyx.ask("net.fetch", {"url": "https://ejemplo.com/"})

@nyx.tool
async def ajuste(clave: str) -> object:
    return await nyx.ask("settings.get", {"key": clave})

@nyx.tool
def sin_describir() -> None:
    pass
"""

SPECS: list[dict[str, Any]] = [
    {
        "name": "escena",
        "description": "Cambia de escena.",
        "parameters": {
            "properties": {"nombre": {"type": "string"}, "rapido": {"type": "boolean"}},
            "required": ["nombre"],
        },
    },
    {"name": "clave", "description": "Lee la clave."},
    {"name": "fuera", "description": "Sale a internet."},
    {
        "name": "ajuste",
        "description": "Lee un ajuste.",
        "parameters": {"properties": {"clave": {"type": "string"}}, "required": ["clave"]},
    },
]


def make(tmp: Path, main: str = MAIN, specs: list[dict[str, Any]] = SPECS) -> Path:
    folder = tmp / "ext"
    (folder / "tools").mkdir(parents=True)
    (folder / "manifest.json").write_text(
        json.dumps(
            {
                "id": "x.obs",
                "permissions": ["net:localhost:4455", "secrets"],
                "settings": [{"key": "password", "label": "Contraseña"}],
            }
        ),
        encoding="utf-8",
    )
    (folder / "tools" / "main.py").write_text(main, encoding="utf-8")
    (folder / "tools" / "tools.json").write_text(json.dumps(specs), encoding="utf-8")
    return folder


def test_fake_nyx_answers_and_records(tmp_path: Path) -> None:
    fake = FakeNyx(make(tmp_path))
    fake.answer("ws.open", 7)
    fake.answer("ws.send", None)
    fake.answer("secrets.get", lambda p: f"clave de {p['key']}")
    assert fake.run("escena", nombre="Juego") == {"escena": "Juego", "rapido": False, "sock": 7}
    assert fake.asked("ws.send") == [{"id": 7, "text": "Juego"}]
    assert fake.run("clave") == "clave de password"  # desde una herramienta normal
    assert sys.modules["nyx"] is nyx  # el `nyx` de verdad sigue en su sitio


def test_fake_nyx_says_no_without_permission(tmp_path: Path) -> None:
    fake = FakeNyx(make(tmp_path))
    with pytest.raises(PermissionDeniedError, match=r"net:ejemplo\.com:443"):
        fake.run("fuera")
    fake = FakeNyx(make(tmp_path / "b"), permissions=[])
    with pytest.raises(PermissionDeniedError, match="secrets"):
        fake.run("clave")


def test_fake_nyx_checks_arguments_like_nyx(tmp_path: Path) -> None:
    fake = FakeNyx(make(tmp_path))
    fake.answer("ws.open", 1)
    fake.answer("ws.send", None)
    with pytest.raises(TypeError, match="falta"):
        fake.run("escena")
    with pytest.raises(TypeError, match="boolean"):
        fake.run("escena", nombre="a", rapido=1)
    with pytest.raises(TypeError, match="no tiene"):
        fake.run("escena", nombre="a", otro=1)
    with pytest.raises(LookupError, match=r"tools\.json"):
        fake.run("sin_describir")  # Nyx no la ofrecería


def test_fake_nyx_catches_a_described_tool_without_code(tmp_path: Path) -> None:
    specs = [*SPECS, {"name": "fantasma", "description": "No existe."}]
    with pytest.raises(LookupError, match="fantasma"):
        FakeNyx(make(tmp_path, specs=specs)).load()


def test_fake_nyx_needs_an_answer(tmp_path: Path) -> None:
    fake = FakeNyx(make(tmp_path))
    with pytest.raises(RuntimeError, match="answer"):
        fake.run("escena", nombre="a")


def test_fake_nyx_settings(tmp_path: Path) -> None:
    fake = FakeNyx(make(tmp_path), settings={"password": "1234"})
    assert fake.run("ajuste", clave="password") == "1234"
    assert FakeNyx(make(tmp_path / "b")).run("ajuste", clave="password") is None
    with pytest.raises(RuntimeError, match="manifiesto"):
        fake.run("ajuste", clave="otra")


# --- Las extensiones oficiales (7.14) -----------------------------------------------------------

OFFICIAL = sorted(p.parent for p in (ROOT / "extensions").glob("*/manifest.json"))


@pytest.mark.parametrize("folder", OFFICIAL, ids=lambda p: p.name)
def test_official_extensions_validate_and_pack(tmp_path: Path, folder: Path) -> None:
    assert nyx_ext.validate(folder)
    out = tmp_path / f"{folder.name}.nyxext"
    nyx_ext.pack(folder, out)
    names = zipfile.ZipFile(out).namelist()
    assert "tools/main.py" in names and not any(n.startswith("tests/") for n in names)


def _restricted_package(tmp_path: Path, why: dict[str, str] | None) -> Path:
    folder = tmp_path / "pide"
    nyx_ext.new(folder, "prueba.pide", "tools")
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    manifest["permissions"] = [*manifest.get("permissions", []), "clipboard:read"]
    if why is not None:
        manifest["why"] = why
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    out = tmp_path / "pide.nyxext"
    nyx_ext.pack(folder, out)
    return out


def test_request_sends_what_tepnyx_needs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    package = _restricted_package(tmp_path, {"clipboard:read": "Para traducir lo copiado."})
    monkeypatch.setattr(nyx_ext, "tepnyx_endpoint", lambda: ("https://x.supabase.co", "clave"))
    sent: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        sent.append(req)
        return httpx.Response(200, json="0b6f6c1e-6a7e-4c4e-9c1b-3f0a2d9e8b11")

    number = nyx_ext.request(
        package,
        "https://ejemplo.com/pide.nyxext",
        "dev@ejemplo.com",
        transport=httpx.MockTransport(handler),
    )
    assert number == "0b6f6c1e-6a7e-4c4e-9c1b-3f0a2d9e8b11"
    req = sent[0]
    assert req.url.path == "/rest/v1/rpc/extension_request"
    assert req.headers["Content-Profile"] == "nyx"
    body = json.loads(req.content)["p_request"]
    assert body["id"] == "prueba.pide"
    assert "clipboard:read" in body["permissions"]
    assert body["why"] == {"clipboard:read": "Para traducir lo copiado."}
    assert body["tools"] and body["tools"][0]["name"]
    assert len(body["sha256"]) == 64


def test_request_needs_a_reason_and_a_delicate_permission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(SystemExit):  # sin «why» ni siquiera valida
        _restricted_package(tmp_path, None)
    folder = tmp_path / "normal"
    nyx_ext.new(folder, "prueba.normal", "tools")
    out = tmp_path / "normal.nyxext"
    nyx_ext.pack(folder, out)
    with pytest.raises(SystemExit, match="no necesita aprobación"):
        nyx_ext.build_request(out, "https://e.com/x", "dev@ejemplo.com")


def test_request_without_tepnyx_leaves_a_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _restricted_package(tmp_path, {"clipboard:read": "Para traducir lo copiado."})
    monkeypatch.setattr(nyx_ext, "tepnyx_endpoint", lambda: None)
    assert nyx_ext.request(package, "https://e.com/x", "dev@ejemplo.com") is None
    saved = json.loads(package.with_suffix(".solicitud.json").read_text(encoding="utf-8"))
    assert saved["contact"] == "dev@ejemplo.com"


def test_status_shows_the_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    monkeypatch.setattr(nyx_ext, "tepnyx_endpoint", lambda: ("https://x.supabase.co", "clave"))
    answer = {"status": "aprobada", "approved": ["clipboard:read"], "reply": "Ok"}
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=answer))
    got = nyx_ext.status("0b6f6c1e-6a7e-4c4e-9c1b-3f0a2d9e8b11", transport=transport)
    assert got["approved"] == ["clipboard:read"]
    with pytest.raises(SystemExit):
        nyx_ext.status("no-es-un-numero")


def test_fake_nyx_controls_only_its_app(tmp_path: Path) -> None:
    folder = tmp_path / "control"
    nyx_ext.new(folder, "prueba.control", "tools")
    fake = FakeNyx(folder, permissions=["apps:control:spotify", "llm"])
    fake._check_permission("apps.keys", {"app": "Spotify", "keys": "space"})
    fake._check_permission("llm.ask", {"prompt": "Hola"})
    with pytest.raises(PermissionDeniedError):
        fake._check_permission("apps.window", {"app": "discord", "action": "focus"})
    with pytest.raises(PermissionDeniedError):
        fake._check_permission("audio.volume", {"level": 10})
