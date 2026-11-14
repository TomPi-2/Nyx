"""Lista de revocación de extensiones: descargar, comprobar y guardar (tarea 7.08).

Como mucho una vez al día y solo si hay alguna extensión firmada instalada (las de modo
desarrollador no cuentan): así Nyx no se conecta a nada si no hace falta (SPEC §8). La lista
va firmada por Tepnyx y nunca se acepta una más vieja que la guardada (`serial`), para que
nadie pueda «desrevocar» una extensión sirviendo una lista antigua.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import httpx

from nyx.ext.signing import RevocationList, SignatureError, verify_revocations
from nyx.paths import local_dir

log = logging.getLogger(__name__)

#: Dónde la publica Tepnyx (la web aún no la sirve: hasta entonces, 404 y no pasa nada).
REVOCATION_URL = "https://tepnyx.com/nyx/extensiones/revocadas.json"
EVERY_S = 24 * 3600
TIMEOUT_S = 10.0
MAX_BYTES = 512 * 1024


def cache_dir() -> Path:
    return local_dir() / "extensions"


def load_cached(
    folder: Path | None = None, trusted: dict[str, str] | None = None
) -> RevocationList | None:
    folder = folder or cache_dir()
    try:
        raw = (folder / "revocadas.json").read_bytes()
        sig = (folder / "revocadas.sig").read_bytes()
        return verify_revocations(raw, sig, trusted)
    except OSError, SignatureError, ValueError:
        return None


def due(folder: Path | None = None, now: float | None = None) -> bool:
    """¿Toca descargarla? (más de un día desde la última vez que se intentó)."""
    stamp = (folder or cache_dir()) / "revocadas.intento"
    try:
        last = stamp.stat().st_mtime
    except OSError:
        return True
    return (now or time.time()) - last >= EVERY_S


async def refresh(
    client: httpx.AsyncClient,
    folder: Path | None = None,
    trusted: dict[str, str] | None = None,
    url: str = REVOCATION_URL,
) -> RevocationList | None:
    """Descarga la lista; devuelve la vigente (la nueva si vale y no es más vieja, si no la
    guardada)."""
    folder = folder or cache_dir()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "revocadas.intento").touch()
    current = load_cached(folder, trusted)
    try:
        r = await client.get(url, timeout=TIMEOUT_S)
        s = await client.get(url.removesuffix(".json") + ".sig", timeout=TIMEOUT_S)
        r.raise_for_status()
        s.raise_for_status()
        if len(r.content) > MAX_BYTES or len(s.content) > 4096:
            raise ValueError("demasiado grande")
        fresh = verify_revocations(r.content, s.content, trusted)
    except (httpx.HTTPError, SignatureError, ValueError) as e:
        log.info("Lista de revocación: no se ha podido actualizar (%s)", e)
        return current
    if current is not None and fresh.serial < current.serial:
        log.warning("Lista de revocación más vieja que la guardada: se ignora")
        return current
    for name, blob in (("revocadas.json", r.content), ("revocadas.sig", s.content)):
        tmp = folder / f"{name}.tmp"
        tmp.write_bytes(blob)
        os.replace(tmp, folder / name)
    return fresh
