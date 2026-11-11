"""SystemIndex: resuelve nombres («vscode», «el lol», «descargas») a cosas que se pueden abrir.

- Al arrancar carga la caché de disco (instantáneo) y reescanea en segundo plano.
- Búsqueda difusa con rapidfuzz sobre todos los alias en memoria (< 5 ms con miles).
- Desempate por uso: lo que más abres gana cuando dos nombres puntúan igual.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz import fuzz, process

from nyx.index.aliases import normalize, strip_articles
from nyx.index.db import SCAN_VERSION, IndexDB
from nyx.index.model import Entry, Kind
from nyx.index.scanners import ScanResult, scan_all
from nyx.paths import local_dir

log = logging.getLogger(__name__)

RESCAN_EVERY_S = 24 * 3600
# SPEC sección 6: el router ejecuta sin LLM con puntuación > 90 y sin empate.
# Alias tan cortos (siglas) solo cuentan si coinciden exactos: si no, «steam» encaja con «ea».
SHORT_ALIAS = 3
CONFIDENT_SCORE = 90.0
TIE_MARGIN = 3.0
MIN_SCORE = 60.0
# Entre dos nombres iguales, mejor la app o el juego que una web o una carpeta.
_KIND_BONUS = {Kind.GAME: 0.6, Kind.APP: 0.5, Kind.FOLDER: 0.2, Kind.SETTING: 0.1, Kind.WEB: 0.0}


def similarity(query: str, alias: str, **_: object) -> float:
    """Parecido 0–100 entre lo dicho y un alias.

    Cuenta que la consulta esté dentro de un alias más largo («code» → «visual studio
    code»), pero no al revés: si no, «la impresora 3d de marte» encajaría con «impresora».
    """
    score = max(fuzz.ratio(query, alias), fuzz.token_sort_ratio(query, alias))
    if len(alias) > len(query):
        score = max(score, fuzz.partial_ratio(query, alias) * 0.95)
    return float(score)


def index_path() -> Path:
    return local_dir() / "cache" / "index.db"


@dataclass(frozen=True, slots=True)
class Match:
    entry: Entry
    score: float  # 0–100 (+ desempate por uso y tipo)
    alias: str


def dedupe(entries: Iterable[Entry]) -> list[Entry]:
    """Quita repetidos: un juego de un lanzador gana al acceso directo con el mismo nombre, y
    una página de Configuración a la app que se llama igual («Configuración»)."""
    entries = list(entries)
    by_key: dict[str, Entry] = {}
    preferred = {normalize(e.name) for e in entries if e.kind in (Kind.GAME, Kind.SETTING)}
    for e in entries:
        if e.kind is Kind.APP and normalize(e.name) in preferred:
            continue
        by_key.setdefault(e.key, e)
    return list(by_key.values())


MIN_FUZZY_LEN = 3  # consultas más cortas: solo coincidencia exacta


class SystemIndex:
    def __init__(
        self,
        db: IndexDB,
        scanner: Callable[[], list[Entry] | ScanResult] = scan_all,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._db = db
        self._scanner = scanner
        self._clock = clock
        self._entries: dict[str, Entry] = {}
        self._choices: list[str] = []  # alias normalizados
        self._owners: list[str] = []  # key de la entrada de cada alias
        self._uses: dict[str, int] = {}
        self._lock = asyncio.Lock()

    @classmethod
    def open(cls, path: Path | None = None) -> SystemIndex:
        index = cls(IndexDB(path or index_path()))
        index.load()
        return index

    def close(self) -> None:
        self._db.close()

    # --- carga y escaneo ---

    def load(self) -> None:
        self._set_entries(self._db.entries())

    def _set_entries(self, entries: list[Entry]) -> None:
        self._entries = {e.key: e for e in entries}
        choices: list[str] = []
        owners: list[str] = []
        for e in entries:
            for alias in e.aliases:
                choices.append(alias)
                owners.append(e.key)
        for alias, key in self._db.user_aliases().items():
            if key in self._entries:
                choices.append(alias)
                owners.append(key)
        self._choices, self._owners = choices, owners
        self._uses = self._db.usage()

    def last_scan(self) -> float | None:
        """Cuándo fue el último escaneo (marca de tiempo), para Ajustes → Caché."""
        return self._db.last_scan()

    def needs_scan(self) -> bool:
        last = self._db.last_scan()
        return (
            last is None
            or self._clock() - last > RESCAN_EVERY_S
            or not self._entries
            or self._db.scan_version() != SCAN_VERSION
        )

    async def refresh(self) -> int:
        """Escanea todas las fuentes en un hilo y sustituye la caché. Devuelve cuántas hay."""
        async with self._lock:
            t0 = time.perf_counter()
            scanned = await asyncio.to_thread(self._scanner)
            if isinstance(scanned, ScanResult):
                found, failed = scanned.entries, scanned.failed
            else:
                found, failed = scanned, set()
            if failed:
                kept = [e for e in self._entries.values() if e.source in failed]
                log.warning("Se conservan %d entradas de %s (fallo al escanear)", len(kept), failed)
                found += kept
            entries = dedupe(found)
            await asyncio.to_thread(self._db.replace_entries, entries)
            self._set_entries(entries)
            log.info(
                "Caché del sistema: %d entradas en %.1f s", len(entries), time.perf_counter() - t0
            )
            return len(entries)

    # --- consulta ---

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, key: str) -> Entry | None:
        return self._entries.get(key)

    def entries(self, kinds: set[Kind] | None = None) -> list[Entry]:
        return [e for e in self._entries.values() if kinds is None or e.kind in kinds]

    def resolve(self, query: str, kinds: set[Kind] | None = None, limit: int = 5) -> list[Match]:
        q = strip_articles(normalize(query))
        if not q:
            return []
        allowed = [
            i
            for i, key in enumerate(self._owners)
            if kinds is None or self._entries[key].kind in kinds
        ]
        if not allowed:
            return []
        exact = [(self._choices[i], 100.0, i) for i in allowed if self._choices[i] == q]
        choices = {i: self._choices[i] for i in allowed if len(self._choices[i]) > SHORT_ALIAS}
        # Con menos de 3 letras solo vale el nombre exacto: «ábrela» dejaba «la», que se
        # parecía a «Calculadora» o a «Aimlabs» (ERRORES.md, 2026-11-11).
        found = (
            process.extract(q, choices, scorer=similarity, limit=40, score_cutoff=MIN_SCORE)
            if len(q) >= MIN_FUZZY_LEN
            else []
        )
        best: dict[str, Match] = {}
        for alias, score, i in [*exact, *found]:
            key = self._owners[i]
            entry = self._entries[key]
            if alias == q:
                score = 100.0
            total = float(score) + min(self._uses.get(key, 0), 20) * 0.1 + _KIND_BONUS[entry.kind]
            if key not in best or total > best[key].score:
                best[key] = Match(entry, total, alias)
        return sorted(best.values(), key=lambda m: m.score, reverse=True)[:limit]

    def confident(self, matches: list[Match]) -> Match | None:
        """La mejor coincidencia si es clara (> 90 y sin empate), o None."""
        if not matches or matches[0].score < CONFIDENT_SCORE:
            return None
        if len(matches) > 1 and matches[0].score - matches[1].score < TIE_MARGIN:
            return None
        return matches[0]

    # --- aprendizaje ---

    def record_use(self, key: str) -> None:
        self._db.record_use(key, self._clock())
        self._uses[key] = self._uses.get(key, 0) + 1

    def add_user_alias(self, alias: str, key: str) -> None:
        alias = normalize(alias)
        if alias and key in self._entries:
            self._db.set_user_alias(alias, key)
            self._choices.append(alias)
            self._owners.append(key)
