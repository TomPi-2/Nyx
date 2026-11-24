"""El cerebro de Nyx en el primer arranque: el LoRA adoptado (`nyx-r2:7b`, 6.27), no el Qwen
de serie (9.08b).

El GGUF va partido en trozos de menos de 2 GB en una Release de GitHub (el límite por
archivo), con su huella cada uno (`nyx/brain/data/cerebro.json`, lo escribe
`scripts/export_brain.py`). Aquí:

1. Si Ollama ya lo tiene, nada.
2. Se bajan los trozos a `%LOCALAPPDATA%\\Nyx\\models\\cerebro` con reanudación (si se corta,
   sigue donde iba) y se comprueba cada uno.
3. Se le dan a Ollama de un tirón (`/api/blobs`, que vuelve a comprobar la huella del total)
   y se crea el modelo con la misma plantilla, sistema y licencia que `qwen2.5:7b`
   (`/api/create`): igual que en el PC donde se entrenó.
4. Los trozos van a la papelera (nunca borrado permanente).

Si algo falla (por ejemplo, la Release aún no está publicada), quien llama baja el modelo de
siempre y Nyx funciona igual.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx
from send2trash import send2trash

from nyx import errors
from nyx.paths import models_dir

log = logging.getLogger(__name__)

MANIFEST = Path(__file__).resolve().parents[1] / "brain" / "data" / "cerebro.json"
RELEASES = "https://github.com/TomPi-2/Nyx/releases/download"
CHUNK = 1 << 20
MB = 1_000_000

#: (descargado, total) en MB.
Progress = Callable[[float, float], Awaitable[None]]


class BrainError(Exception):
    pass


def manifest() -> dict[str, Any] | None:
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None
    return data if isinstance(data, dict) and data.get("parts") else None


def folder() -> Path:
    return models_dir() / "cerebro"


async def installed(
    host: str, name: str, transport: httpx.AsyncBaseTransport | None = None
) -> bool:
    try:
        async with httpx.AsyncClient(timeout=3, transport=transport) as http:
            resp = await http.get(f"{host}/api/tags")
            names = {str(m.get("name")) for m in resp.json().get("models", [])}
    except httpx.HTTPError, ValueError:
        return False
    return name in names


async def ensure(
    host: str,
    progress: Progress,
    *,
    root: Path | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> str:
    """Deja el cerebro de Nyx en Ollama y devuelve su nombre. BrainError si no se puede."""
    data = manifest()
    if data is None:
        raise BrainError("Esta versión no trae el cerebro de Nyx")
    name = str(data["name"])
    if await installed(host, name, transport):
        return name
    base = root or folder()
    files = await _download_parts(data, base, progress, transport)
    await _give_to_ollama(host, data, files, transport)
    _trash(files)
    log.info("Cerebro de Nyx listo en Ollama: %s", name)
    return name


def gguf_path(root: Path | None = None) -> Path:
    """Dónde queda el cerebro en un solo archivo para llama-server (C5.1): los trozos
    «nyx-r2-7b.gguf.001»… se unen en «nyx-r2-7b.gguf»."""
    data = manifest()
    name = str(data["parts"][0]["file"]).rsplit(".", 1)[0] if data else "nyx.gguf"
    return (root or folder()) / name


async def ensure_file(
    progress: Progress,
    *,
    root: Path | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Path:
    """Deja el cerebro de Nyx en un `.gguf` para llama-server (sin Ollama) y devuelve su ruta.

    Se bajan los trozos (con reanudación y huella cada uno), se unen y se comprueba la huella
    del total; los trozos van a la papelera. BrainError si no se puede."""
    data = manifest()
    if data is None:
        raise BrainError("Esta versión no trae el cerebro de Nyx")
    base = root or folder()
    target = gguf_path(base)
    size, sha = int(data["size"]), str(data["sha256"])
    if await asyncio.to_thread(_size_of, target) == size:
        return target  # ya estaba (la huella se comprobó al unirlo)
    files = await _download_parts(data, base, progress, transport)
    partial = target.with_name(target.name + ".part")
    if await asyncio.to_thread(_join, files, partial) != sha:
        send2trash(str(partial))
        raise BrainError(f"{errors.BRAIN_JOIN} · El cerebro unido no coincide con su huella")
    partial.replace(target)
    _trash(files)
    log.info("Cerebro de Nyx listo: %s", target)
    return target


async def _download_parts(
    data: dict[str, Any],
    base: Path,
    progress: Progress,
    transport: httpx.AsyncBaseTransport | None,
) -> list[Path]:
    await asyncio.to_thread(base.mkdir, parents=True, exist_ok=True)
    parts: list[dict[str, Any]] = list(data["parts"])
    total = sum(int(p["size"]) for p in parts)
    done = 0
    async with httpx.AsyncClient(
        follow_redirects=True, timeout=httpx.Timeout(30.0, read=120.0), transport=transport
    ) as http:
        for part in parts:
            path = base / str(part["file"])
            url = f"{RELEASES}/{data['release']}/{part['file']}"
            await _download(http, url, path, part, done, total, progress)
            done += int(part["size"])
        await progress(total / MB, total / MB)
    return [base / str(p["file"]) for p in parts]


def _join(files: list[Path], target: Path) -> str:
    """Une los trozos en `target` y devuelve la huella SHA-256 del total."""
    h = hashlib.sha256()
    with target.open("wb") as out:
        for f in files:
            with f.open("rb") as src:
                while block := src.read(CHUNK * 4):
                    h.update(block)
                    out.write(block)
    return h.hexdigest()


def _trash(files: list[Path]) -> None:
    for f in files:
        try:
            send2trash(str(f))
        except OSError:
            log.warning("No he podido llevar %s a la papelera", f.name)


async def _download(
    http: httpx.AsyncClient,
    url: str,
    path: Path,
    part: dict[str, Any],
    before: int,
    total: int,
    progress: Progress,
) -> None:
    size, sha = int(part["size"]), str(part["sha256"])
    if await asyncio.to_thread(_already, path, size, sha):
        return  # ya estaba (una descarga anterior)
    partial = path.with_name(path.name + ".part")
    have = await asyncio.to_thread(_size_of, partial)
    if have > size:  # no cuadra con lo esperado: se empieza ese trozo de nuevo
        send2trash(str(partial))
        have = 0
    headers = {"Range": f"bytes={have}-"} if have else {}
    try:
        async with http.stream("GET", url, headers=headers) as resp:
            if resp.status_code == 404:
                raise BrainError("El cerebro de Nyx aún no está publicado")
            resp.raise_for_status()
            if have and resp.status_code != 206:
                have = 0  # el servidor no reanuda: desde el principio
            mode = "ab" if have else "wb"
            last = 0.0
            with partial.open(mode) as out:
                async for chunk in resp.aiter_bytes(CHUNK):
                    out.write(chunk)
                    have += len(chunk)
                    now = (before + have) / MB
                    if now - last >= 8:  # cada 8 MB
                        last = now
                        await progress(now, total / MB)
    except httpx.HTTPError as e:
        raise BrainError(f"No he podido bajar {part['file']}: {e}") from e
    if await asyncio.to_thread(_sha256, partial) != sha:
        send2trash(str(partial))
        raise BrainError(f"{part['file']}: la huella no coincide")
    partial.replace(path)


def _already(path: Path, size: int, sha: str) -> bool:
    return path.exists() and path.stat().st_size == size and _sha256(path) == sha


def _size_of(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(CHUNK * 4), b""):
            h.update(block)
    return h.hexdigest()


async def _give_to_ollama(
    host: str,
    data: dict[str, Any],
    files: list[Path],
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    digest = f"sha256:{data['sha256']}"

    async def body() -> AsyncIterator[bytes]:
        for f in files:
            with f.open("rb") as src:
                while block := src.read(CHUNK * 4):
                    yield block

    timeout = httpx.Timeout(60.0, read=1800.0, write=1800.0)
    async with httpx.AsyncClient(timeout=timeout, transport=transport) as http:
        try:
            have = await http.head(f"{host}/api/blobs/{digest}")
            if have.status_code != 200:
                # Ollama comprueba que el total tiene esta huella; si no, lo rechaza.
                up = await http.post(f"{host}/api/blobs/{digest}", content=body())
                up.raise_for_status()
            request = {
                "model": data["name"],
                "files": {"nyx.gguf": digest},
                "template": data.get("template", ""),
                "system": data.get("system", ""),
                "license": data.get("license", ""),
                "stream": False,
            }
            made = await http.post(f"{host}/api/create", json=request)
            made.raise_for_status()
        except httpx.HTTPError as e:
            raise BrainError(f"Ollama no ha podido crear el cerebro: {e}") from e
