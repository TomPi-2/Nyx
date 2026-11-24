r"""Baja llama-server (llama.cpp, MIT) para Windows con Vulkan, versión fija y huella (C5.1).

    uv run python scripts/fetch_llama.py                 # → %LOCALAPPDATA%\Nyx\llama
    uv run python scripts/fetch_llama.py --out D:\llama  # otra carpeta (build-release.ps1)

Es la compilación oficial de llama.cpp (GitHub Releases de ggml-org), no una nuestra: ya trae
las variantes de la CPU (ggml-cpu-*.dll, de SSE4.2 a AVX-512) y se carga la que sirve, el
problema que tuvimos con whisper-server compilado con GGML_NATIVE. Se fija una versión de
hace unas semanas, no la del día: llama.cpp publica varias al día.

Solo se copian llama-server.exe, sus DLL y las licencias; el resto de programas del zip
(llama-cli, llama-bench…) no hacen falta. Lo de antes en la carpeta va a la papelera.

Para cambiar de versión: TAG, el nombre del zip y su SHA-256 (la API de GitHub lo da en
`assets[].digest`), y volver a medir con battery.py y game_bench.py.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import sys
import zipfile
from pathlib import Path

import httpx
from send2trash import send2trash

TAG = "b12240"  # 2026-11-10
ZIP = f"llama-{TAG}-bin-win-vulkan-x64.zip"
SHA256 = "9ea8f113961f32024e0c34409432d3bd350590b040259520bb0b98aeba3a8ac7"
URL = f"https://github.com/ggml-org/llama.cpp/releases/download/{TAG}/{ZIP}"
LICENSE_URL = f"https://raw.githubusercontent.com/ggml-org/llama.cpp/{TAG}/LICENSE"


def wanted(name: str) -> bool:
    """llama-server.exe, las DLL que usa y las licencias (no las de los otros programas)."""
    lower = name.lower()
    if "/" in lower:
        return False
    if lower == "llama-server.exe" or lower.startswith("license"):
        return True
    if lower.endswith("-impl.dll"):
        return lower == "llama-server-impl.dll"
    return lower.endswith(".dll")


def extract(data: bytes, out: Path) -> list[str]:
    out.mkdir(parents=True, exist_ok=True)
    names: list[str] = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for info in z.infolist():
            if info.is_dir() or not wanted(info.filename):
                continue
            (out / info.filename).write_bytes(z.read(info))
            names.append(info.filename)
    (out / "VERSION.txt").write_text(f"llama.cpp {TAG}\n{ZIP}\nsha256 {SHA256}\n", "utf-8")
    return names


def default_out() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Nyx" / "llama"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=default_out())
    args = parser.parse_args(argv)
    out: Path = args.out.resolve()
    if (out / "VERSION.txt").is_file() and TAG in (out / "VERSION.txt").read_text("utf-8"):
        print(f"Ya está llama.cpp {TAG} en {out}")
        return 0
    print(f"Bajando {ZIP}…")
    resp = httpx.get(URL, follow_redirects=True, timeout=httpx.Timeout(30.0, read=300.0))
    resp.raise_for_status()
    if hashlib.sha256(resp.content).hexdigest() != SHA256:
        print("La huella no coincide: no se usa", file=sys.stderr)
        return 1
    if out.exists():
        send2trash(str(out))  # nunca borrado permanente
    names = extract(resp.content, out)
    # El zip no trae la licencia de llama.cpp (MIT): la de esa misma versión, al lado.
    lic = httpx.get(LICENSE_URL, follow_redirects=True, timeout=30.0)
    lic.raise_for_status()
    (out / "LICENSE-llama.cpp.txt").write_text(lic.text, "utf-8")
    print(f"llama-server ({TAG}) en {out}: {len(names) + 1} archivos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
