"""Escáneres de la caché: cada uno devuelve las entradas de una fuente (SPEC sección 10).

`installed` (registro Uninstall) queda fuera de la fase 3a: todo lo que tenía acceso directo
ya sale en shell:AppsFolder; se añadirá si aparecen programas sin acceso que se quieran abrir.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from nyx.index.model import Entry
from nyx.index.scanners import apps, folders, games, tables

log = logging.getLogger(__name__)

SCANNERS: dict[str, Callable[[], list[Entry]]] = {
    "apps": apps.scan,
    "games": games.scan,
    "folders": folders.scan,
    "settings": tables.scan_settings,
    "websites": tables.scan_websites,
}


def scan_all() -> list[Entry]:
    entries: list[Entry] = []
    for name, scanner in SCANNERS.items():
        try:
            entries += scanner()
        except Exception:
            log.warning("Fallo en el escáner %s", name, exc_info=True)
    return entries
