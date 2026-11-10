"""Descarga los datos de entrenamiento (datasets.py), con reanudación y huella SHA-256.

    uv run python training/download.py            # todo (~6 GB)
    uv run python training/download.py --solo oww piper-davefx

Si una fuente aún no tiene la huella fijada, la imprime al final para copiarla en datasets.py.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))

from datasets import SOURCES, Source, data_dir

from nyx.models import safe_extract

CHUNK = 1 << 20


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(CHUNK):
            h.update(block)
    return h.hexdigest()


def fetch(source: Source, http: httpx.Client) -> str:
    """Descarga (o reanuda) y verifica. Devuelve la huella."""
    final = source.path()
    if final.exists():
        return source.sha256 or "(ya estaba)"
    folder = data_dir() / source.key
    folder.mkdir(parents=True, exist_ok=True)
    part = folder / (source.filename + ".part")
    done = part.stat().st_size if part.exists() else 0
    headers = {"Range": f"bytes={done}-"} if done else {}
    with http.stream("GET", source.url, headers=headers) as resp:
        if resp.status_code == 416:  # ya estaba completo
            pass
        else:
            resp.raise_for_status()
            if done and resp.status_code != 206:
                done = 0  # el servidor no reanuda: desde cero
            total = done + int(resp.headers.get("content-length", 0))
            mode = "ab" if done else "wb"
            with part.open(mode) as out:
                last = -1
                for chunk in resp.iter_bytes(CHUNK):
                    out.write(chunk)
                    done += len(chunk)
                    pct = int(100 * done / total) if total else 0
                    if pct // 10 != last:
                        last = pct // 10
                        print(f"  {source.filename}: {pct} %", flush=True)
    digest = sha256_of(part)
    if source.sha256 and digest != source.sha256:
        part.unlink()
        raise RuntimeError(f"{source.filename}: la huella SHA-256 no coincide")
    if source.extract:
        safe_extract(part, folder)
        part.unlink()
        final.write_text(digest, encoding="ascii")  # marcador: descomprimido entero
    else:
        part.replace(final)
    return digest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--solo", nargs="*", help="solo estas claves (oww, piper-davefx, rirs…)")
    args = parser.parse_args()
    chosen = [s for s in SOURCES if not args.solo or s.key in args.solo]
    unpinned: list[tuple[Source, str]] = []
    timeout = httpx.Timeout(30.0, read=300.0)
    with httpx.Client(follow_redirects=True, timeout=timeout) as http:
        for source in chosen:
            print(f"{source.key}: {source.filename} ({source.license})", flush=True)
            digest = fetch(source, http)
            if not source.sha256 and len(digest) == 64:
                unpinned.append((source, digest))
    if unpinned:
        print("\nHuellas para fijar en datasets.py:")
        for source, digest in unpinned:
            print(f"  {source.filename}: {digest}")
    print(f"\nListo: {data_dir()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
