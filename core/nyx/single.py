r"""Un solo núcleo escuchando: si queda uno anterior vivo, se cierra.

Pasó en la fase 3c: «Reiniciar núcleo» mataba solo `uv` y el núcleo viejo seguía escuchando;
cada frase se atendía dos veces (y uno de ellos con código antiguo). La app ya mata el árbol
entero; esto es la segunda red. El PID se guarda en %LOCALAPPDATA%\Nyx\core.pid y solo se cierra
un proceso si de verdad es un núcleo lanzado por la app (python con «--parent-pipe»).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import psutil

from nyx.paths import local_dir

log = logging.getLogger(__name__)


def pid_file() -> Path:
    return local_dir() / "core.pid"


def _is_nyx_core(proc: psutil.Process) -> bool:
    try:
        # «--parent-pipe» solo lo lleva el núcleo lanzado por la app (no pytest, no --ask).
        return "python" in proc.name().lower() and "--parent-pipe" in proc.cmdline()
    except psutil.Error:
        return False


def take_over(path: Path | None = None, *, me: int | None = None) -> bool:
    """Cierra el núcleo anterior si sigue vivo y apunta este. Devuelve si había que cerrar."""
    path = path or pid_file()
    me = me if me is not None else os.getpid()
    closed = False
    try:
        old = int(path.read_text(encoding="ascii").strip())
    except OSError, ValueError:
        old = 0
    if old and old != me and psutil.pid_exists(old):
        try:
            proc = psutil.Process(old)
            if _is_nyx_core(proc) and me not in {p.pid for p in proc.children(recursive=True)}:
                log.warning("Había otro núcleo de Nyx en marcha (PID %d): se cierra", old)
                family = [*proc.children(recursive=True), proc]
                for p in family:
                    p.kill()
                psutil.wait_procs(family, timeout=5)
                closed = True
        except psutil.Error:
            pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(me), encoding="ascii")
    return closed
