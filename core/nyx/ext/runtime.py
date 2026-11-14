r"""El Python de las extensiones con código y sus carpetas (tarea 7.06).

- `%LOCALAPPDATA%\Nyx\ext-runtime\python-<versión>`: el Python «embeddable» oficial (PSF-2.0,
  firmado por la Python Software Foundation), descargado con su huella SHA-256. Es la 3.14
  (no la 3.12 del núcleo): la 3.12 ya no publica binarios con parches. Las extensiones traen
  sus dependencias para esta versión (`tools/lib`).
- `%LOCALAPPDATA%\Nyx\ext-runtime\nyx_runner.py`: el programa que corre dentro (runner.py).
- `%LOCALAPPDATA%\Nyx\ext-data\<id>`: la única carpeta en la que una extensión puede escribir.

El Python y el programa no tienen nada privado: se pueden leer desde cualquier AppContainer
(«ALL APPLICATION PACKAGES», como `C:\Program Files`). El paquete y los datos de cada
extensión, solo desde el suyo (sandbox.py).
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import subprocess
import uuid
from pathlib import Path

import httpx

from nyx.models import DownloadError, safe_extract
from nyx.paths import local_dir

log = logging.getLogger(__name__)

PYTHON_VERSION = "3.14.10"
PYTHON_URL = (
    f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
)
PYTHON_SHA256 = "90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159"
PYTHON_MB = 12

#: SID de «ALL APPLICATION PACKAGES»: cualquier AppContainer.
ALL_APP_PACKAGES = "*S-1-15-2-1"

RUNNER_SOURCE = Path(__file__).with_name("runner.py")


def runtime_dir() -> Path:
    return local_dir() / "ext-runtime"


def python_dir(root: Path | None = None) -> Path:
    return (root or runtime_dir()) / f"python-{PYTHON_VERSION}"


def data_root() -> Path:
    return local_dir() / "ext-data"


def data_dir(ext_id: str, root: Path | None = None) -> Path:
    return (root or data_root()) / ext_id


def ensure_python(root: Path | None = None, *, client: httpx.Client | None = None) -> Path:
    """Descarga y verifica el Python de las extensiones si falta. Devuelve su carpeta.

    Bloquea (descarga ~12 MB): desde asyncio, con `asyncio.to_thread`.
    """
    root = root or runtime_dir()
    final = python_dir(root)
    if (final / "python.exe").exists():
        return final
    root.mkdir(parents=True, exist_ok=True)
    part = root / f"python-{PYTHON_VERSION}.{uuid.uuid4().hex}.part"
    staging = root / f".python-{PYTHON_VERSION}.{uuid.uuid4().hex}.tmp"
    own = client is None
    http = client or httpx.Client(follow_redirects=True, timeout=httpx.Timeout(30.0, read=120.0))
    try:
        digest = hashlib.sha256()
        with http.stream("GET", PYTHON_URL) as resp, part.open("wb") as out:
            resp.raise_for_status()
            for chunk in resp.iter_bytes(1 << 20):
                out.write(chunk)
                digest.update(chunk)
        if digest.hexdigest() != PYTHON_SHA256:
            raise DownloadError("el Python de las extensiones no tiene la huella esperada")
        safe_extract(part, staging)
        if not (staging / "python.exe").exists():
            raise DownloadError("el Python de las extensiones viene sin python.exe")
        os.replace(staging, final)
    except httpx.HTTPError as e:
        raise DownloadError(f"Python de las extensiones: {e}") from e
    finally:
        if own:
            http.close()
        part.unlink(missing_ok=True)
        if staging.exists():  # a medio descomprimir: a la papelera, como todo en Nyx
            from send2trash import send2trash

            with contextlib.suppress(OSError):
                send2trash(str(staging))
    grant(final, ALL_APP_PACKAGES, "RX")
    log.info("Python de las extensiones listo (%s)", PYTHON_VERSION)
    return final


def ensure_runner(root: Path | None = None) -> Path:
    """Copia el programa de dentro (runner.py) si falta o ha cambiado con Nyx."""
    root = root or runtime_dir()
    target = root / "nyx_runner.py"
    source = RUNNER_SOURCE.read_bytes()
    if not target.exists() or target.read_bytes() != source:
        root.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(f".{uuid.uuid4().hex}.tmp")
        tmp.write_bytes(source)
        os.replace(tmp, target)
        grant(target, ALL_APP_PACKAGES, "RX", inherit=False)
    return target


def grant(path: Path, sid: str, rights: str, *, inherit: bool = True) -> None:
    """Da permiso a un SID («*S-1-15-…») sobre una carpeta (y lo que contiene) o un archivo."""
    flags = "(OI)(CI)" if inherit else ""
    subprocess.run(
        ["icacls", str(path), "/grant", f"{sid}:{flags}{rights}", "/q"],
        check=True,
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
