r"""Empaqueta el núcleo para instalarlo sin `uv` (tarea 9.07).

    uv run python scripts/package_core.py            # → ../dist/app/core
    uv run python scripts/package_core.py --out D:\x  # en otra carpeta

Resultado (lo que va junto al ejecutable de la app, `core_process.rs` lo busca ahí):

    core/
      python/            Python 3.14 «embeddable» oficial (PSF-2.0, firmado por la PSF),
                         comprobado con su SHA-256, y las dependencias en Lib\site-packages
      app/nyx/           el código del núcleo, ya compilado a .pyc
      bin/whisper/       whisper-server.exe compilado con Vulkan y sus DLL (MIT; `--whisper`
                         o NYX_WHISPER_DIR: la carpeta Release de whisper.cpp, compilada sin
                         GGML_NATIVE para que funcione en cualquier procesador)
      build.json         versión de Python, huella del uv.lock y fecha

- Las dependencias salen de `uv.lock` (las mismas versiones que en desarrollo) con sus huellas
  (`--require-hashes`): nada que no esté bloqueado entra en el paquete.
- `python314._pth` fija dónde busca Python (su zip, `Lib\site-packages` y `..\app`) y activa
  `site` para que pywin32 cargue sus DLL. Se lanza con `-I`: sin variables de entorno ni la
  carpeta del usuario.
- Si la carpeta de salida ya existe, va a la papelera (nunca se borra para siempre).
- Al acabar, una prueba de humo: importa el núcleo y las dependencias pesadas con ese Python.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import httpx
from send2trash import send2trash

from nyx.ext.runtime import PYTHON_SHA256, PYTHON_URL, PYTHON_VERSION

CORE = Path(__file__).resolve().parents[1]
REPO = CORE.parent
DEFAULT_OUT = REPO / "dist" / "app" / "core"
CACHE = REPO / "dist" / "cache"
TAG = "".join(PYTHON_VERSION.split(".")[:2])  # «314»

#: Lo que se importa en la prueba de humo: el núcleo y lo que suele fallar al empaquetar
#: (DLL de pywin32, extensiones en C, torch, onnxruntime, WinRT).
SMOKE = (
    "import nyx.main, nyx.services, nyx.pipeline, torch, onnxruntime, pocket_tts, piper, "
    "win32api, pythoncom, sounddevice, winrt.windows.foundation, rapidfuzz, cryptography; "
    "print('ok', __import__('sys').version.split()[0])"
)


def fetch_python() -> Path:
    """El zip oficial, en caché y comprobado (el mismo que el de las extensiones, 7.06)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / Path(PYTHON_URL).name
    if not target.exists() or _sha256(target) != PYTHON_SHA256:
        print(f"Descargando {PYTHON_URL}")
        part = target.with_suffix(".part")
        with httpx.stream("GET", PYTHON_URL, follow_redirects=True, timeout=60) as r:
            r.raise_for_status()
            with part.open("wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
        if _sha256(part) != PYTHON_SHA256:
            send2trash(str(part))
            raise SystemExit("La huella del Python descargado no coincide: no se usa.")
        part.replace(target)
    return target


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def unpack_python(archive: Path, python: Path) -> None:
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            dest = (python / name).resolve()
            if not dest.is_relative_to(python.resolve()):
                raise SystemExit(f"Ruta fuera de la carpeta en el zip: {name}")
        z.extractall(python)
    # Dónde busca Python. Rutas relativas a esta carpeta; «import site» procesa los .pth
    # de Lib\site-packages (pywin32 añade ahí sus DLL).
    (python / f"python{TAG}._pth").write_text(
        f"python{TAG}.zip\n.\nLib\\site-packages\n..\\app\nimport site\n", encoding="utf-8"
    )


def install_dependencies(site_packages: Path) -> str:
    """Las de `uv.lock` (sin las de desarrollo ni el propio núcleo), con sus huellas."""
    lock = CORE / "uv.lock"
    with tempfile.TemporaryDirectory() as tmp:
        req = Path(tmp) / "requirements.txt"
        subprocess.run(
            [
                "uv", "export", "--project", str(CORE), "--frozen", "--no-dev",
                "--no-emit-project", "--format", "requirements-txt", "-o", str(req),
            ],
            check=True,
        )  # fmt: skip
        subprocess.run(
            [
                "uv", "pip", "install", "--target", str(site_packages),
                "--python-version", PYTHON_VERSION, "--python-platform",
                "x86_64-pc-windows-msvc", "--require-hashes", "--no-deps",
                "--link-mode", "copy", "-r", str(req),
            ],
            check=True,
        )  # fmt: skip
    return _sha256(lock)


def copy_whisper(source: Path, dest: Path) -> int:
    """whisper-server.exe y las DLL que necesita (ggml, Vulkan…); nada más de la carpeta."""
    if not (source / "whisper-server.exe").is_file():
        raise SystemExit(f"No está whisper-server.exe en {source}")
    dest.mkdir(parents=True)
    files = [source / "whisper-server.exe", *sorted(source.glob("*.dll"))]
    for f in files:
        shutil.copy2(f, dest / f.name)
    return len(files)


def copy_core(app: Path) -> None:
    shutil.copytree(
        CORE / "nyx",
        app / "nyx",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )


def compile_core(python_exe: Path, app: Path) -> None:
    """Los .pyc del núcleo ya hechos: arranca antes la primera vez."""
    subprocess.run(
        [str(python_exe), "-I", "-m", "compileall", "-q", "-j", "0", str(app)], check=True
    )


def smoke(python_exe: Path) -> str:
    result = subprocess.run(
        [str(python_exe), "-I", "-X", "utf8", "-c", SMOKE],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0 or not result.stdout.startswith("ok"):
        raise SystemExit(f"La prueba de humo ha fallado:\n{result.stderr[-3000:]}")
    help_run = subprocess.run(
        [str(python_exe), "-I", "-X", "utf8", "-m", "nyx", "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if help_run.returncode != 0:
        raise SystemExit(f"`python -m nyx --help` ha fallado:\n{help_run.stderr[-3000:]}")
    return result.stdout.strip()


def size_mb(path: Path) -> float:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1e6


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--whisper",
        type=Path,
        default=Path(os.environ["NYX_WHISPER_DIR"]) if "NYX_WHISPER_DIR" in os.environ else None,
        help="carpeta con whisper-server.exe y sus DLL (si no, el paquete va sin él)",
    )
    args = parser.parse_args(argv)
    out: Path = args.out.resolve()
    started = time.perf_counter()

    if out.exists():
        print(f"{out} ya existe: a la papelera")
        send2trash(str(out))
    python, app = out / "python", out / "app"
    python.mkdir(parents=True)
    app.mkdir()

    unpack_python(fetch_python(), python)
    lock_sha = install_dependencies(python / "Lib" / "site-packages")
    copy_core(app)
    if args.whisper is not None:
        count = copy_whisper(args.whisper, out / "bin" / "whisper")
        print(f"whisper-server: {count} archivos")
    else:
        print("Aviso: sin --whisper, el paquete no lleva whisper-server (no podrá oír)")
    python_exe = python / "python.exe"
    compile_core(python_exe, app)
    smoke_out = smoke(python_exe)
    (out / "build.json").write_text(
        json.dumps(
            {
                "python": PYTHON_VERSION,
                "uv_lock_sha256": lock_sha,
                "built": time.strftime("%Y-%m-%dT%H:%M:%S"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Prueba de humo: {smoke_out}")
    print(f"Núcleo empaquetado en {out}: {size_mb(out):.0f} MB")
    print(f"Tiempo: {time.perf_counter() - started:.0f} s")


if __name__ == "__main__":
    sys.exit(main())
