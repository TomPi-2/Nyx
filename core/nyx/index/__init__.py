"""SystemIndex: caché SQLite de apps, juegos, carpetas, páginas de Configuración y webs."""

from nyx.index.model import Entry, Kind, Launch, LaunchKind
from nyx.index.service import Match, SystemIndex

__all__ = ["Entry", "Kind", "Launch", "LaunchKind", "Match", "SystemIndex"]
