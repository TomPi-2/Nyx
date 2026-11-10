r"""Registro de activaciones y ajuste automático del umbral (SPEC sección 4.7, fase 4d).

- Cada activación queda en %LOCALAPPDATA%\Nyx\activaciones\AAAA-MM-DD.jsonl: hora, detector,
  puntuación, si whisper la confirmó y qué oyó. Solo en este equipo.
- «Nyx, eso no era para ti» marca la activación anterior como error y sube el umbral un
  poco (ERROR_STEP, como mucho MAX_OFFSET). El ajuste se guarda en activacion.json y vale
  también tras reiniciar. En la fase 5, el botón «esto fue un error» hará lo mismo.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from nyx.index.aliases import normalize
from nyx.paths import local_dir

ERROR_STEP = 0.03
MAX_OFFSET = 0.2
ERROR_WINDOW_S = 120.0  # «eso no era para ti» se refiere a una activación reciente

NOT_FOR_YOU = re.compile(
    r"^(?:eso\s+|esto\s+)?no\s+(?:era|iba|es)\s+(?:para\s+ti|contigo)$"
    r"|^no\s+te\s+(?:he\s+llamado|llamaba|llame|estaba\s+llamando|hablaba)$"
    r"|^no\s+(?:hablaba|estaba\s+hablando)\s+contigo$"
    r"|^falsa\s+alarma$|^te\s+has\s+activado\s+sin\s+querer$|^nadie\s+te\s+ha\s+llamado$"
)


def is_not_for_you(text: str) -> bool:
    return bool(NOT_FOR_YOU.match(normalize(text)))


@dataclass
class Activation:
    id: str
    at: float  # time.time()
    score: float | None


class ActivationLog:
    def __init__(self, folder: Path, state: Path) -> None:
        self.folder = folder
        self.state = state
        self.offset = self._load_offset()
        self.recent: list[Activation] = []

    @classmethod
    def default(cls) -> ActivationLog:
        return cls(local_dir() / "activaciones", local_dir() / "activacion.json")

    def _load_offset(self) -> float:
        try:
            data = json.loads(self.state.read_text(encoding="utf-8"))
            return min(MAX_OFFSET, max(0.0, float(data.get("ajuste_umbral", 0.0))))
        except (OSError, ValueError, TypeError):
            return 0.0

    def _write(self, entry: dict[str, object]) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / f"{datetime.now():%Y-%m-%d}.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def record(
        self, engine: str, score: float | None, verified: bool | None, heard: str = ""
    ) -> Activation:
        activation = Activation(uuid.uuid4().hex[:10], time.time(), score)
        self._write(
            {
                "id": activation.id,
                "hora": datetime.now().isoformat(timespec="seconds"),
                "detector": engine,
                "puntuacion": None if score is None else round(score, 3),
                "confirmada": verified,
                "oido": heard,
            }
        )
        if verified is not False:
            self.recent = [*self.recent[-4:], activation]
        return activation

    def mark_previous_error(self, now: float | None = None) -> float | None:
        """La activación anterior a la actual fue un error: se anota y se sube el umbral.
        Devuelve el ajuste nuevo, o None si no había ninguna reciente."""
        now = now or time.time()
        # La última es la de «Nyx, eso no era para ti»: la errónea es la de antes.
        candidates = [a for a in self.recent[:-1] if now - a.at <= ERROR_WINDOW_S]
        if not candidates:
            return None
        wrong = candidates[-1]
        self.recent.remove(wrong)
        self._write(
            {"id": wrong.id, "error": True, "hora": datetime.now().isoformat(timespec="seconds")}
        )
        self.offset = min(MAX_OFFSET, self.offset + ERROR_STEP)
        self.state.parent.mkdir(parents=True, exist_ok=True)
        self.state.write_text(json.dumps({"ajuste_umbral": self.offset}), encoding="utf-8")
        return self.offset
