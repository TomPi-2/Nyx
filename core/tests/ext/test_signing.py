"""7.08: firma de las extensiones, modo desarrollador y lista de revocación."""

from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nyx.ext import revocation
from nyx.ext.signing import (
    RevocationList,
    SignatureError,
    sign_revocations,
    verify_package,
    verify_revocations,
)
from nyx.ext.store import ExtensionStore, PackageError
from tests.ext.conftest import TEST_KEY, TRUSTED, signed

MANIFEST = {
    "id": "alguien.prueba",
    "name": "Prueba",
    "version": "1.0.0",
    "author": "Alguien",
    "nyx_api": "1.0",
    "kinds": ["knowledge"],
}


def package(tmp: Path, *, sign: bool = True) -> Path:
    path = tmp / "p.nyxext"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("manifest.json", json.dumps(MANIFEST))
        zf.writestr("knowledge/a.md", "## A\n\nTexto.")
    return signed(path) if sign else path


def store(tmp: Path) -> ExtensionStore:
    return ExtensionStore(tmp / "ext", tmp / "s.json", trash=lambda p: None, trusted_keys=TRUSTED)


def test_a_signed_package(tmp_path: Path) -> None:
    assert verify_package(package(tmp_path), trusted=TRUSTED) == "prueba-1"
    assert store(tmp_path).install(package(tmp_path), accept=True).status == "installed"


def test_unsigned_only_in_developer_mode(tmp_path: Path) -> None:
    s = store(tmp_path)
    with pytest.raises(PackageError, match="modo desarrollador"):
        s.install(package(tmp_path, sign=False))
    s.install(package(tmp_path, sign=False), accept=True, dev=True)
    found = s.get("alguien.prueba")
    assert found is not None and found.state.dev  # «sin revisar»


def test_a_changed_file_breaks_the_signature(tmp_path: Path) -> None:
    path = package(tmp_path)
    tampered = tmp_path / "t.nyxext"
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(tampered, "w") as dst:
        for info in src.infolist():
            blob = src.read(info)
            dst.writestr(info, b"## A\n\nOtro." if info.filename == "knowledge/a.md" else blob)
    with pytest.raises(SignatureError, match="ha cambiado"):
        verify_package(tampered, trusted=TRUSTED)


def test_an_added_file_breaks_the_signature(tmp_path: Path) -> None:
    path = package(tmp_path)
    with zipfile.ZipFile(path, "a") as zf:
        zf.writestr("tools/extra.py", "print('hola')")
    with pytest.raises(SignatureError):
        verify_package(path, trusted=TRUSTED)


def test_a_key_that_is_not_tepnyx(tmp_path: Path) -> None:
    other = {"prueba-1": TRUSTED["prueba-1"][:-4] + "AAA="}
    with pytest.raises(SignatureError):
        verify_package(package(tmp_path), trusted=other)
    with pytest.raises(SignatureError, match="no es de Tepnyx"):
        verify_package(package(tmp_path), trusted={})


# --- revocación ---


def revocations(serial: int, *ids: str) -> tuple[bytes, bytes]:
    data = {
        "serial": serial,
        "issued": datetime(2026, 11, 14, tzinfo=UTC).isoformat(),
        "revoked": [{"id": i, "reason": "dañina"} for i in ids],
    }
    raw = json.dumps(data).encode()
    return raw, sign_revocations(raw, TEST_KEY, "prueba-1")


def test_revocation_list_signature() -> None:
    raw, sig = revocations(1, "alguien.prueba")
    found = verify_revocations(raw, sig, TRUSTED)
    assert found.reason("alguien.prueba", "1.0.0") == "dañina"
    assert found.reason("otro.cual", "1.0.0") is None
    forged = Ed25519PrivateKey.generate()
    bad = sign_revocations(raw, forged, "prueba-1")
    with pytest.raises(SignatureError):
        verify_revocations(raw, bad, TRUSTED)


async def test_refresh_keeps_the_newest(tmp_path: Path) -> None:
    lists = {"new": revocations(5, "a.b"), "old": revocations(3)}
    which = ["new"]

    def handler(request: httpx.Request) -> httpx.Response:
        raw, sig = lists[which[0]]
        return httpx.Response(200, content=sig if request.url.path.endswith(".sig") else raw)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        got = await revocation.refresh(client, tmp_path, TRUSTED)
        assert got is not None and got.serial == 5
        which[0] = "old"  # alguien sirve una lista vieja para «desrevocar»
        got = await revocation.refresh(client, tmp_path, TRUSTED)
        assert got is not None and got.serial == 5
    assert revocation.load_cached(tmp_path, TRUSTED) == got


async def test_refresh_without_network_keeps_the_saved_one(tmp_path: Path) -> None:
    def ok(request: httpx.Request) -> httpx.Response:
        raw, sig = revocations(2)
        return httpx.Response(200, content=sig if request.url.path.endswith(".sig") else raw)

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin red")

    async with httpx.AsyncClient(transport=httpx.MockTransport(ok)) as client:
        await revocation.refresh(client, tmp_path, TRUSTED)
    async with httpx.AsyncClient(transport=httpx.MockTransport(down)) as client:
        got = await revocation.refresh(client, tmp_path, TRUSTED)
    assert isinstance(got, RevocationList) and got.serial == 2
    assert not revocation.due(tmp_path)  # ya se intentó hoy


async def test_a_revoked_extension_is_not_loaded(tmp_path: Path) -> None:
    from nyx.ext.manager import ExtensionManager
    from nyx.tools.registry import default_registry

    s = store(tmp_path)
    s.install(package(tmp_path), accept=True)

    async def apply(selector: object) -> None:
        return None

    manager = ExtensionManager(s, default_registry(), budget_chars=27033, apply_selector=apply)
    raw, sig = revocations(1, "alguien.prueba")
    manager.set_revocations(verify_revocations(raw, sig, TRUSTED))
    await manager.reload()
    (status,) = manager.status()
    assert not status.active and "retirado" in status.problems[0]
