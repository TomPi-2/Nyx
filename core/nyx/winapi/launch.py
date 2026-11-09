"""Abrir apps, webs, carpetas y páginas de Configuración como procesos independientes.

Nyx vive en un job object que mata a sus hijos al salir (ver winjob.py). Todo lo que abre
para el usuario tiene que salir de ese job, o se cerraría al cerrar Nyx: por eso se lanza
con CREATE_BREAKAWAY_FROM_JOB, y lo que abre el shell (apps, URIs, carpetas) pasa por
explorer.exe, que delega en el Explorador que ya está en marcha.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from collections.abc import Sequence

from nyx.index.model import Launch, LaunchKind

log = logging.getLogger(__name__)


def spawn_detached(args: Sequence[str]) -> None:
    """Lanza un proceso que sobrevive a Nyx. Lanza OSError si no se puede."""
    if sys.platform != "win32":
        subprocess.Popen(list(args), start_new_session=True)
        return
    base = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    last: OSError | None = None
    for flags in (base | subprocess.CREATE_BREAKAWAY_FROM_JOB, base):
        try:
            subprocess.Popen(
                list(args),
                creationflags=flags,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            return
        except OSError as e:
            last = e
    assert last is not None
    raise last


def shell_open(target: str) -> None:
    """Abre con el Explorador: `shell:AppsFolder\\<AppID>`, URIs (https:, steam:, ms-settings:)
    o rutas. Lo abre el Explorador del usuario, no Nyx."""
    spawn_detached(["explorer.exe", target])


def open_app_id(app_id: str) -> None:
    shell_open(f"shell:AppsFolder\\{app_id}")


def launch(spec: Launch) -> None:
    """Abre una entrada de la caché según cómo se lanza."""
    if spec.kind is LaunchKind.APPS_FOLDER:
        open_app_id(spec.value)
    elif spec.kind is LaunchKind.EXE:
        spawn_detached([spec.value, *spec.args])
    else:
        shell_open(spec.value)
