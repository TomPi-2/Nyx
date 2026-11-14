r"""Registro de activaciones y ajuste automático del umbral (SPEC sección 4.7, fase 4d).

- Cada activación queda en %LOCALAPPDATA%\Nyx\activaciones\AAAA-MM-DD.jsonl: hora, detector,
  puntuación, si whisper la confirmó y qué oyó. Solo en este equipo.
- «Nyx, eso no era para ti» marca la activación anterior como error y sube el umbral un
  poco (ERROR_STEP, como mucho MAX_OFFSET). El ajuste se guarda en activacion.json y vale
  también tras reiniciar. En la fase 5, el botón «esto fue un error» hará lo mismo.
- Si whisper descarta varias seguidas, el umbral sube solo un poco y vuelve a bajar cuando
  pasa una hora tranquila (6.22). Con `wake.save_false_clips`, se guarda su audio.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
import wave
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from nyx.index.aliases import normalize
from nyx.paths import local_dir

log = logging.getLogger(__name__)

ERROR_STEP = 0.03
MAX_OFFSET = 0.2
ERROR_WINDOW_S = 120.0  # «eso no era para ti» se refiere a una activación reciente

# Subida automática (6.22): si whisper descarta AUTO_COUNT activaciones en AUTO_WINDOW_S, el
# umbral sube AUTO_STEP (como mucho AUTO_MAX); tras AUTO_DECAY_S sin descartes baja AUTO_STEP.
# Simulado con 568 activaciones reales del 10 al 12-11: quita la mitad de las falsas (485 →
# 247) y pierde 3 de 83 buenas. Solo en memoria: al reiniciar, vuelve a empezar.
AUTO_STEP = 0.03
AUTO_COUNT = 3
AUTO_WINDOW_S = 600.0
AUTO_MAX = 0.15
AUTO_DECAY_S = 3600.0

# Audio de las falsas activaciones (opcional, `wake.save_false_clips`): para reentrenar el
# detector con el ruido real de casa. Solo en este equipo; se quedan los últimos MAX_CLIPS.
MAX_CLIPS = 500
CLIP_RATE = 16_000

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
    def __init__(self, folder: Path, state: Path, *, save_clips: bool = False) -> None:
        self.folder = folder
        self.state = state
        self.offset = self._load_offset()
        self.recent: list[Activation] = []
        self.save_clips = save_clips
        self._auto = 0.0  # subida automática vigente
        self._auto_since = 0.0  # desde cuándo cuenta la bajada (último descarte o escalón)
        self._discards: list[float] = []

    @property
    def clips(self) -> Path:
        return self.folder / "audio"

    def auto_offset(self, now: float | None = None) -> float:
        """La subida automática ahora: baja AUTO_STEP por cada AUTO_DECAY_S sin descartes."""
        now = time.time() if now is None else now
        steps = int((now - self._auto_since) // AUTO_DECAY_S)
        if self._auto > 0 and steps > 0:
            self._auto = max(0.0, round(self._auto - steps * AUTO_STEP, 3))
            self._auto_since += steps * AUTO_DECAY_S
        return self._auto

    def _discarded(self, now: float) -> None:
        self.auto_offset(now)  # aplica antes la bajada pendiente
        self._auto_since = now
        self._discards = [t for t in self._discards if now - t <= AUTO_WINDOW_S] + [now]
        if len(self._discards) >= AUTO_COUNT:
            self._discards = []
            self._auto = min(AUTO_MAX, round(self._auto + AUTO_STEP, 3))

    @classmethod
    def default(cls) -> ActivationLog:
        return cls(local_dir() / "activaciones", local_dir() / "activacion.json")

    def _load_offset(self) -> float:
        try:
            data = json.loads(self.state.read_text(encoding="utf-8"))
            return min(MAX_OFFSET, max(0.0, float(data.get("ajuste_umbral", 0.0))))
        except OSError, ValueError, TypeError:
            return 0.0

    def _write(self, entry: dict[str, object]) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / f"{datetime.now():%Y-%m-%d}.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def record(
        self,
        engine: str,
        score: float | None,
        verified: bool | None,
        heard: str = "",
        clip: np.ndarray[Any, Any] | None = None,
        *,
        now: float | None = None,
    ) -> Activation:
        """Apunta una activación. `verified=False` (whisper no oyó «Nyx») cuenta para la
        subida automática y, con `save_clips`, guarda su audio (`clip`, int16 a 16 kHz)."""
        activation = Activation(uuid.uuid4().hex[:10], time.time() if now is None else now, score)
        if verified is False:
            self._discarded(activation.at)
            if self.save_clips and clip is not None and len(clip):
                self._save_clip(activation.id, clip)
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

    def _save_clip(self, activation_id: str, clip: np.ndarray[Any, Any]) -> None:
        """Guarda el audio y deja solo los últimos MAX_CLIPS (son archivos de Nyx, no del
        usuario: se quitan los más viejos para que la carpeta no crezca sin fin)."""
        try:
            self.clips.mkdir(parents=True, exist_ok=True)
            with wave.open(str(self.clips / f"{activation_id}.wav"), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(CLIP_RATE)
                w.writeframes(np.asarray(clip, dtype=np.int16).tobytes())
            saved = sorted(self.clips.glob("*.wav"), key=lambda p: p.stat().st_mtime)
            for old in saved[:-MAX_CLIPS]:
                old.unlink(missing_ok=True)
        except OSError:
            log.warning("No se pudo guardar el audio de la activación", exc_info=True)

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
