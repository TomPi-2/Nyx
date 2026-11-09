"""Activación provisional con Vosk y gramática restringida (fase 2; en la fase 4, modelo propio).

La gramática incluye palabras parecidas: si el audio se parece más a una de ellas, Vosk la
elige a ella y no a «nix», lo que reduce las falsas activaciones. «no», «existe»… se añadieron
porque «no existe» activaba a Nyx (probado con audio sintetizado: deja de activarse y «nix»
se sigue detectando). Después, whisper confirma la palabra (ver pipeline.py).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from nyx.audio.capture import SAMPLE_RATE, Frame

log = logging.getLogger(__name__)

DISTRACTORS = ("ni", "mix", "six", "nike", "no", "existe", "nos", "nunca", "nada")


def heard(text: str, word: str) -> bool:
    return word.casefold() in text.casefold().split()


class VoskWakeWord:
    def __init__(self, model_dir: Path, word: str = "nix") -> None:
        from vosk import KaldiRecognizer, Model, SetLogLevel

        SetLogLevel(-1)
        self._word = word
        grammar = [word, *(d for d in DISTRACTORS if d != word), "[unk]"]
        self._rec: Any = KaldiRecognizer(Model(str(model_dir)), SAMPLE_RATE, json.dumps(grammar))

    def process(self, frame: Frame) -> bool:
        final = self._rec.AcceptWaveform(frame.tobytes())
        result = json.loads(self._rec.Result() if final else self._rec.PartialResult())
        text = str(result.get("text") or result.get("partial") or "")
        if heard(text, self._word):
            log.debug("Activación (Vosk): %r", text)
            self.reset()
            return True
        return False

    def reset(self) -> None:
        self._rec.Reset()
