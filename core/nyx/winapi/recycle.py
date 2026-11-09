"""Recuperar de la papelera lo que Nyx acaba de mandar allí (deshacer de delete_files).

Cada elemento de la papelera guarda su carpeta y su nombre originales
(System.Recycle.DeletedFrom y System.FileName); el verbo «undelete» lo devuelve a su sitio.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

RECYCLE_BIN = 10  # CSIDL_BITBUCKET


def _key(folder: str, name: str) -> tuple[str, str]:
    return folder.rstrip("\\/").casefold(), name.casefold()


def restore(paths: list[Path]) -> list[Path]:
    """Restaura esas rutas (la versión borrada más reciente de cada una). Devuelve las que
    han vuelto. Si ya existe algo en la ruta original, no se toca."""
    import pythoncom
    import win32com.client

    wanted = {_key(str(p.parent), p.name): p for p in paths}
    pythoncom.CoInitialize()
    try:
        bin_ = win32com.client.Dispatch("Shell.Application").NameSpace(RECYCLE_BIN)
        newest: dict[tuple[str, str], tuple[Any, Any]] = {}
        for item in bin_.Items():
            folder = item.ExtendedProperty("System.Recycle.DeletedFrom")
            name = item.ExtendedProperty("System.FileName")
            if not folder or not name:
                continue
            key = _key(str(folder), str(name))
            if key not in wanted:
                continue
            when = item.ExtendedProperty("System.Recycle.DateDeleted")
            if key not in newest or (when and str(when) > str(newest[key][0])):
                newest[key] = (when, item)
        restored = []
        for key, (_, item) in newest.items():
            target = wanted[key]
            if target.exists():
                log.warning("No restauro %s: ya hay algo con ese nombre", target)
                continue
            item.InvokeVerb("undelete")
            restored.append(target)
        return restored
    finally:
        pythoncom.CoUninitialize()
