"""Corte del texto en frases mientras llega del LLM, para empezar a hablar cuanto antes."""

from __future__ import annotations

import re

_END = ".!?…"
_PAUSE = ",;:"
# Tras una coma solo se corta si el trozo ya es largo: cortes muy cortos suenan entrecortados.
MIN_CLAUSE_CHARS = 40
# Etiquetas que no terminan frase aunque lleven punto.
_ABBREV = re.compile(r"\b(?:sr|sra|dr|dra|etc|ej|p\. ej|aprox|núm|pág)\.$", re.IGNORECASE)


class SentenceSplitter:
    def __init__(self, min_clause_chars: int = MIN_CLAUSE_CHARS) -> None:
        self._buf = ""
        self._min_clause = min_clause_chars

    def feed(self, text: str) -> list[str]:
        """Añade texto y devuelve las frases completas que ya se pueden decir."""
        self._buf += text
        out: list[str] = []
        start = 0
        # Un signo solo cierra frase cuando ya se ve el carácter siguiente (un espacio):
        # así «3.5» o «...» no cortan antes de tiempo.
        for i in range(len(self._buf) - 1):
            ch, nxt = self._buf[i], self._buf[i + 1]
            if not nxt.isspace():
                continue
            piece = self._buf[start : i + 1].strip()
            sentence_end = ch in _END and not _ABBREV.search(piece)
            long_clause = ch in _PAUSE and len(piece) >= self._min_clause
            if sentence_end or long_clause:
                out.append(piece)
                start = i + 1
        self._buf = self._buf[start:]
        return [p for p in out if _speakable(p)]

    def flush(self) -> str | None:
        rest, self._buf = self._buf.strip(), ""
        return rest if _speakable(rest) else None


def _speakable(text: str) -> bool:
    return any(c.isalnum() for c in text)
