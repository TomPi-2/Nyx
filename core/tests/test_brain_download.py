"""El cerebro de Nyx en el primer arranque (9.08b): trozos con reanudación y huella, Ollama
lo crea con la plantilla de Qwen, y si no está publicado se baja el de siempre."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import httpx
import pytest

from nyx.setup import brain

HOST = "http://ollama.test"
DATA = b"GGUF" + bytes(range(256)) * 40  # un «cerebro» de 10 KB


def fake_manifest(parts: list[bytes]) -> dict[str, Any]:
    return {
        "name": "nyx-r2:7b",
        "release": "cerebro-r2",
        "sha256": hashlib.sha256(b"".join(parts)).hexdigest(),
        "size": sum(len(p) for p in parts),
        "parts": [
            {"file": f"nyx.gguf.{i:03d}", "size": len(p), "sha256": hashlib.sha256(p).hexdigest()}
            for i, p in enumerate(parts, start=1)
        ],
        "template": "{{ .Prompt }}",
        "system": "Sistema",
        "license": "Apache-2.0",
    }


class Server:
    """Las Releases de GitHub (con Range) y la API de Ollama, de mentira."""

    def __init__(self, parts: list[bytes], *, published: bool = True) -> None:
        self.parts = {f"nyx.gguf.{i:03d}": p for i, p in enumerate(parts, start=1)}
        self.published = published
        self.uploaded = b""
        self.created: dict[str, Any] | None = None
        self.ranges: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "/cerebro-r2/" in path:
            name = path.rsplit("/", 1)[-1]
            if not self.published or name not in self.parts:
                return httpx.Response(404)
            body = self.parts[name]
            if rng := request.headers.get("range"):
                self.ranges.append(rng)
                start = int(rng.removeprefix("bytes=").rstrip("-"))
                return httpx.Response(206, content=body[start:])
            return httpx.Response(200, content=body)
        if path == "/api/tags":
            return httpx.Response(200, json={"models": []})
        if path.startswith("/api/blobs/") and request.method == "HEAD":
            return httpx.Response(404)
        if path.startswith("/api/blobs/"):
            self.uploaded = request.read()
            want = path.rsplit(":", 1)[-1]
            ok = hashlib.sha256(self.uploaded).hexdigest() == want
            return httpx.Response(201 if ok else 400)
        if path == "/api/create":
            import json

            self.created = json.loads(request.read())
            return httpx.Response(200, json={"status": "success"})
        return httpx.Response(404)


@pytest.fixture
def trashed(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    out: list[str] = []
    monkeypatch.setattr(brain, "send2trash", out.append)
    return out


async def noop(_done: float, _total: float) -> None:
    pass


async def test_downloads_checks_and_creates_in_ollama(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, trashed: list[str]
) -> None:
    parts = [DATA[:4000], DATA[4000:8000], DATA[8000:]]
    monkeypatch.setattr(brain, "manifest", lambda: fake_manifest(parts))
    server = Server(parts)
    name = await brain.ensure(HOST, noop, root=tmp_path, transport=httpx.MockTransport(server))
    assert name == "nyx-r2:7b"
    assert server.uploaded == DATA  # Ollama recibe el GGUF entero, en orden
    assert server.created is not None
    assert server.created["files"] == {"nyx.gguf": f"sha256:{hashlib.sha256(DATA).hexdigest()}"}
    assert server.created["template"] == "{{ .Prompt }}"
    assert len(trashed) == 3  # los trozos, a la papelera


async def test_resumes_a_cut_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, trashed: list[str]
) -> None:
    parts = [DATA]
    monkeypatch.setattr(brain, "manifest", lambda: fake_manifest(parts))
    (tmp_path / "nyx.gguf.001.part").write_bytes(DATA[:3000])  # se cortó la conexión
    server = Server(parts)
    await brain.ensure(HOST, noop, root=tmp_path, transport=httpx.MockTransport(server))
    assert server.ranges == ["bytes=3000-"]
    assert server.uploaded == DATA


async def test_a_damaged_part_is_not_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, trashed: list[str]
) -> None:
    parts = [DATA]
    manifest = fake_manifest(parts)
    manifest["parts"][0]["sha256"] = "0" * 64
    monkeypatch.setattr(brain, "manifest", lambda: manifest)
    with pytest.raises(brain.BrainError, match="huella"):
        await brain.ensure(HOST, noop, root=tmp_path, transport=httpx.MockTransport(Server(parts)))
    assert trashed  # lo bajado no se usa: a la papelera


async def test_not_published_yet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    parts = [DATA]
    monkeypatch.setattr(brain, "manifest", lambda: fake_manifest(parts))
    server = Server(parts, published=False)
    with pytest.raises(brain.BrainError, match="publicado"):
        await brain.ensure(HOST, noop, root=tmp_path, transport=httpx.MockTransport(server))


def test_the_real_manifest() -> None:
    """El que va con Nyx: nyx-r2:7b en trozos de menos de 2 GB y con la plantilla de Qwen."""
    data = brain.manifest()
    assert data is not None and data["name"] == "nyx-r2:7b"
    assert all(int(p["size"]) < 2 * 1024**3 for p in data["parts"])
    assert sum(int(p["size"]) for p in data["parts"]) == data["size"]
    assert "<|im_start|>" in data["template"]
