r"""Peticiones corregidas: su audio, lo transcrito y lo que hizo Nyx (plan «Cerebro 2», C0).

Cuando el usuario deshace o corrige lo último («deshazlo», «no, el otro», «te has equivocado»,
«eso no era para ti»), la petición anterior era un error de Nyx. Con
`privacy.save_corrections` (apagado por defecto) se guarda en
%LOCALAPPDATA%\Nyx\aprender\: el audio (`<id>.wav`) y una línea en `correcciones.jsonl` con lo
oído, lo entendido, lo que hizo, lo que dijo y la corrección. Sirve para las rondas de
entrenamiento siguientes. Nunca sale del equipo; pasadas MAX_SAVED, las más viejas van a la
papelera.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
import wave
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np

from nyx.index.aliases import normalize
from nyx.paths import local_dir
from nyx.wake.activations import is_not_for_you

log = logging.getLogger(__name__)

MAX_SAVED = 1000
RATE = 16_000
# Una corrección se refiere a lo de justo antes: pasado este rato, ya no.
WINDOW_S = 120.0


class Kind(StrEnum):
    UNDO = "deshacer"  # «deshazlo»
    CORRECTION = "correccion"  # «no, el otro», «te has equivocado»
    NOT_FOR_ME = "no_era_para_mi"  # «eso no era para ti»


_UNDO = re.compile(
    r"^(?:no\s+)?(?:deshaz(?:lo|la|los|las)?|deshacer|deshace|revierte(?:lo|la)?|"
    r"recuperal[oa]|vuelve\s+a\s+como\s+estaba|ponlo\s+como\s+estaba|control\s+z)$"
)
_CORRECTION = re.compile(
    r"^(?:eso\s+no(?:\s+es\s+lo\s+que\s+te\s+he\s+pedido)?|asi\s+no|no\s+es\s+eso|"
    r"no\s+era\s+eso|no\s+te\s+he\s+(?:pedido|dicho)\s+eso|te\s+has\s+(?:equivocado|confundido)|"
    r"lo\s+has\s+hecho\s+mal|lo\s+has\s+entendido\s+mal|me\s+has\s+entendido\s+mal|"
    r"(?:no\s+)?(?:el|la)\s+otr[oa])\b"
)
# «No, el Spotify», «No, a las siete y media»: un «no» con coma o punto delante de lo demás.
_NO_COMMA = re.compile(r"^\s*no\s*[,.;:!]\s*\S", re.IGNORECASE)


def correction_kind(raw: str) -> Kind | None:
    """¿Corrige esta frase lo anterior? (`raw`: lo transcrito, con su puntuación)."""
    text = normalize(raw)
    if not text:
        return None
    if is_not_for_you(text):
        return Kind.NOT_FOR_ME
    if _UNDO.match(text):
        return Kind.UNDO
    if _CORRECTION.match(text) or _NO_COMMA.match(raw):
        return Kind.CORRECTION
    return None


@dataclass
class _Request:
    at: float
    request: str  # identificador de la petición (el del registro de acciones)
    raw: str
    text: str
    audio: np.ndarray[Any, Any] | None
    saved: bool = False


@dataclass
class CorrectionStore:
    folder: Path
    enabled: bool = False
    # Lo que hizo Nyx con una petición (por su identificador): el registro de acciones.
    actions: Callable[[str], list[dict[str, Any]]] = field(default=lambda _rid: [])
    clock: Callable[[], float] = time.monotonic
    _previous: _Request | None = field(default=None, init=False)
    _current: _Request | None = field(default=None, init=False)

    @classmethod
    def default(cls, *, enabled: bool = False) -> CorrectionStore:
        return cls(local_dir() / "aprender", enabled=enabled)

    def begin(self, request: str, raw: str, text: str, audio: Any = None) -> None:
        """Llega una petición nueva (ya transcrita)."""
        if not self.enabled:
            return
        self._previous = self._current
        clip = None if audio is None else np.asarray(audio, dtype=np.int16)
        self._current = _Request(self.clock(), request, raw, text, clip)

    def check(self, raw: str, *, reply: str = "") -> Kind | None:
        """Si la petición actual corrige la anterior, guarda la anterior. `reply`: lo que dijo
        Nyx a la anterior (de la memoria corta)."""
        if not self.enabled:
            return None
        kind = correction_kind(raw)
        prev = self._previous
        if kind is None or prev is None or prev.saved:
            return kind
        if self.clock() - prev.at > WINDOW_S:
            return kind
        prev.saved = True
        try:
            self._save(prev, kind, raw, reply)
        except OSError:
            log.warning("No se pudo guardar la corrección", exc_info=True)
        return kind

    def _save(self, prev: _Request, kind: Kind, correction: str, reply: str) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        entry_id = uuid.uuid4().hex[:10]
        if prev.audio is not None and prev.audio.size:
            with wave.open(str(self.folder / f"{entry_id}.wav"), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(RATE)
                w.writeframes(prev.audio.tobytes())
        entry = {
            "id": entry_id,
            "hora": datetime.now().isoformat(timespec="seconds"),
            "tipo": kind.value,
            "oido": prev.raw,
            "entendido": prev.text,
            "hizo": [
                {k: a.get(k) for k in ("tool", "params", "decision", "ok", "message")}
                for a in self.actions(prev.request)
            ],
            "dijo": reply,
            "correccion": correction,
        }
        with (self.folder / "correcciones.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        log.info("Corrección guardada (%s): %r", kind.value, prev.text)
        saved = sorted(self.folder.glob("*.wav"), key=lambda p: p.stat().st_mtime)
        if len(saved) > MAX_SAVED:
            from send2trash import send2trash

            # A la papelera, nunca borrado permanente (SPEC sección 8).
            send2trash([str(p) for p in saved[:-MAX_SAVED]])
