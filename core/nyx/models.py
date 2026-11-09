r"""Modelos de IA: catálogo, descarga verificada y rutas en %LOCALAPPDATA%\Nyx\models.

Cada archivo tiene su URL fija y su huella SHA-256: si no coincide, no se usa (SPEC sección 2).
Uso: `uv run nyx --download-models`.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from nyx.paths import models_dir

log = logging.getLogger(__name__)

CHUNK = 1 << 20


@dataclass(frozen=True, slots=True)
class ModelFile:
    key: str
    filename: str
    url: str
    sha256: str
    size_mb: int
    license: str
    # Los .zip se descomprimen en una carpeta con el mismo nombre sin la extensión.
    extract: bool = False

    def path(self, root: Path | None = None) -> Path:
        root = root or models_dir()
        name = self.filename.removesuffix(".zip") if self.extract else self.filename
        return root / name


CATALOG: tuple[ModelFile, ...] = (
    ModelFile(
        key="vad",
        filename="silero_vad.onnx",
        url="https://github.com/snakers4/silero-vad/raw/v5.1.2/src/silero_vad/data/silero_vad.onnx",
        sha256="2623a2953f6ff3d2c1e61740c6cdb7168133479b267dfef114a4a3cc5bdd788f",
        size_mb=2,
        license="MIT",
    ),
    ModelFile(
        key="wake",
        filename="vosk-model-small-es-0.42.zip",
        url="https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip",
        sha256="09b239888f633ef2f0b4e09736e3d9936acfd810bc65d53fad45261762c6511f",
        size_mb=40,
        license="Apache-2.0",
        extract=True,
    ),
    ModelFile(
        key="stt",
        filename="ggml-large-v3-turbo-q5_0.bin",
        url="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo-q5_0.bin",
        sha256="394221709cd5ad1f40c46e6031ca61bce88931e6e088c188294c6d5a55ffa7e2",
        size_mb=547,
        license="MIT",
    ),
    # Voces de Piper (rhasspy/piper-voices). Las CC-BY piden citar la autoría (créditos).
    ModelFile(
        key="voice-sharvard",
        filename="es_ES-sharvard-medium.onnx",
        url="https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/sharvard/medium/es_ES-sharvard-medium.onnx",
        sha256="234dc4cf0fdb53ccb76b9b2c4d7ef1330364762674c1b78c1b62d8608c528a54",
        size_mb=77,
        license="CC-BY-3.0 (datos: Univ. de Edimburgo, Sharvard corpus)",
    ),
    ModelFile(
        key="voice-sharvard-config",
        filename="es_ES-sharvard-medium.onnx.json",
        url="https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/sharvard/medium/es_ES-sharvard-medium.onnx.json",
        sha256="1910940c6b480e0f7cbce5e0da45c8cbe2557ccbfd86a5d22cda141a3b65f521",
        size_mb=1,
        license="CC-BY-3.0 (datos: Univ. de Edimburgo, Sharvard corpus)",
    ),
    ModelFile(
        key="voice-davefx",
        filename="es_ES-davefx-medium.onnx",
        url="https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/davefx/medium/es_ES-davefx-medium.onnx",
        sha256="d2c9224e122321aac3c33343957fff4d0f465226cb74c66b0f520ca3f8c0dd07",
        size_mb=64,
        license="CC0",
    ),
    ModelFile(
        key="voice-davefx-config",
        filename="es_ES-davefx-medium.onnx.json",
        url="https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/davefx/medium/es_ES-davefx-medium.onnx.json",
        sha256="531c4051502e1acbc10b42437f11679bfce9e3919e1796e51fabd73e01e7fd2e",
        size_mb=1,
        license="CC0",
    ),
    ModelFile(
        key="voice-daniela",
        filename="es_AR-daniela-high.onnx",
        url="https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_AR/daniela/high/es_AR-daniela-high.onnx",
        sha256="7ceb1fc0dab349418c5b54a639ae9ee595212d7c9ea422220d8419163d5cc985",
        size_mb=115,
        license="CC-BY-SA-4.0 (datos: OpenSLR 61)",
    ),
    ModelFile(
        key="voice-daniela-config",
        filename="es_AR-daniela-high.onnx.json",
        url="https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_AR/daniela/high/es_AR-daniela-high.onnx.json",
        sha256="aedbf69647e1d754c62ecf8e0366ca5f16af3e768e3c6b5329af6eb6bde3852b",
        size_mb=1,
        license="CC-BY-SA-4.0 (datos: OpenSLR 61)",
    ),
)

MODELS: dict[str, ModelFile] = {m.key: m for m in CATALOG}


class DownloadError(Exception):
    pass


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def is_present(model: ModelFile, root: Path | None = None) -> bool:
    return model.path(root).exists()


def safe_extract(archive: Path, dest: Path) -> None:
    """Descomprime sin dejar que una entrada escriba fuera de `dest` (zip slip)."""
    dest = dest.resolve()
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            target = (dest / member.filename).resolve()
            if not target.is_relative_to(dest):
                raise DownloadError(f"entrada peligrosa en {archive.name}: {member.filename}")
        zf.extractall(dest)


Progress = Callable[[ModelFile, int, int], None]


def download(
    model: ModelFile,
    root: Path | None = None,
    *,
    client: httpx.Client | None = None,
    progress: Progress | None = None,
) -> Path:
    """Descarga, verifica la huella y (si toca) descomprime. Devuelve la ruta final."""
    root = root or models_dir()
    root.mkdir(parents=True, exist_ok=True)
    final = model.path(root)
    if final.exists():
        return final

    part = root / (model.filename + ".part")
    own_client = client is None
    http = client or httpx.Client(follow_redirects=True, timeout=httpx.Timeout(30.0, read=120.0))
    try:
        h = hashlib.sha256()
        with http.stream("GET", model.url) as resp, part.open("wb") as out:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            done = 0
            for chunk in resp.iter_bytes(CHUNK):
                out.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if progress:
                    progress(model, done, total)
        if h.hexdigest() != model.sha256:
            part.unlink(missing_ok=True)
            raise DownloadError(f"{model.filename}: la huella SHA-256 no coincide")
    except httpx.HTTPError as e:
        part.unlink(missing_ok=True)
        raise DownloadError(f"{model.filename}: {e}") from e
    finally:
        if own_client:
            http.close()

    if model.extract:
        try:
            safe_extract(part, root)
        finally:
            part.unlink(missing_ok=True)
        if not final.exists():
            raise DownloadError(f"{model.filename} no contiene la carpeta {final.name}")
    else:
        os.replace(part, final)
    return final


def download_all(root: Path | None = None, skip: frozenset[str] = frozenset()) -> int:
    """Orden `nyx --download-models`: descarga lo que falte mostrando el progreso."""
    failed = 0
    last_pct: dict[str, int] = {}

    def show(model: ModelFile, done: int, total: int) -> None:
        if not total:
            return
        pct = done * 100 // total
        if last_pct.get(model.key) != pct:
            last_pct[model.key] = pct
            print(f"\r  {model.filename}: {pct:3d} %", end="", file=sys.stderr, flush=True)

    for model in CATALOG:
        if model.key in skip:
            print(f"· {model.filename}: ya configurado en los ajustes", file=sys.stderr)
            continue
        if is_present(model, root):
            print(f"· {model.filename}: ya descargado", file=sys.stderr)
            continue
        print(f"· {model.filename} ({model.size_mb} MB, {model.license})", file=sys.stderr)
        try:
            download(model, root, progress=show)
            print(f"\r  {model.filename}: listo        ", file=sys.stderr)
        except (DownloadError, OSError) as e:
            failed += 1
            print(f"\n  Error: {e}", file=sys.stderr)
    return 1 if failed else 0
