"""Escáneres de la caché: cada uno devuelve las entradas de una fuente (SPEC sección 10).

`installed` (registro Uninstall) queda fuera de la fase 3a: todo lo que tenía acceso directo
ya sale en shell:AppsFolder; se añadirá si aparecen programas sin acceso que se quieran abrir.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

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
# Fuentes (Entry.source) que produce cada escáner.
SOURCES: dict[str, set[str]] = {
    "apps": {"apps"},
    "games": {"steam", "riot", "epic"},
    "folders": {"folders"},
    "settings": {"settings"},
    "websites": {"websites"},
}


@dataclass
class ScanResult:
    entries: list[Entry]
    # Fuentes que no se pudieron escanear: la caché conserva lo que tenía de ellas, para que
    # un fallo pasajero no deje a Nyx sin apps («no encuentro Spotify»).
    failed: set[str] = field(default_factory=set)


def scan_all() -> ScanResult:
    # Se ejecuta en un hilo: shell:AppsFolder es COM y cada hilo necesita CoInitialize.
    import pythoncom

    pythoncom.CoInitialize()
    try:
        result = ScanResult([])
        for name, scanner in SCANNERS.items():
            try:
                result.entries += scanner()
            except Exception:
                log.warning("Fallo en el escáner %s", name, exc_info=True)
                result.failed |= SOURCES[name]
        return result
    finally:
        pythoncom.CoUninitialize()
