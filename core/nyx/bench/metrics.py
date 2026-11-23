"""Métricas de la batería de audio: errores de palabras, veredicto de cada frase y percentiles."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from nyx.index.aliases import normalize

# «Nyx» y cómo lo transcribe Whisper: no cuenta en los errores de palabras (se mide aparte).
_WAKE = re.compile(r"^(?:(?:hey|oye|eh)\s+)?(?:nyx|nix|niks|nicks|mix)\b\s*")


def words(text: str) -> list[str]:
    return normalize(text).split()


def strip_wake(text: str) -> str:
    return _WAKE.sub("", normalize(text))


def edit_distance(ref: Sequence[str], hyp: Sequence[str]) -> int:
    """Levenshtein por palabras."""
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h))
        prev = cur
    return prev[-1]


def wer(reference: str, hypothesis: str) -> tuple[int, int]:
    """(errores, palabras de la referencia), sin «Nyx» delante ni signos ni tildes."""
    ref = strip_wake(reference).split()
    hyp = strip_wake(hypothesis).split()
    return edit_distance(ref, hyp), len(ref)


def percentile(values: Sequence[float], p: float) -> float:
    """Percentil con interpolación lineal (p entre 0 y 100); NaN si no hay datos."""
    if not values:
        return math.nan
    s = sorted(values)
    k = (len(s) - 1) * p / 100.0
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


class Verdict(StrEnum):
    BIEN = "bien"  # hizo lo esperado
    PREGUNTO = "pregunto"  # no actuó y preguntó (bien si se esperaba; si no, aceptable)
    MAL = "mal"  # actuó, y no lo que debía: lo peor
    NADA = "nada"  # no hizo nada útil (ni actuó ni preguntó)
    NO_ACTIVO = "no_activo"  # no se activó cuando debía
    SIN_DEBER = "sin_deber"  # contestó o actuó a algo que no era para Nyx


@dataclass(frozen=True)
class Observed:
    activated: bool  # llegó a escuchar la petición (verificación de «Nyx» o seguimiento)
    calls: list[tuple[str, dict[str, Any]]]  # lo que habría ejecutado
    reply: str  # lo que dijo o mostró


def _same(expected: Any, actual: Any) -> bool:
    if isinstance(expected, str) and isinstance(actual, str):
        e, a = normalize(expected), normalize(actual)
        return bool(e) and (e in a or a in e)
    return bool(expected == actual)


def _asks(reply: str) -> bool:
    return "?" in reply


def _calls_match(expected: dict[str, Any], calls: list[tuple[str, dict[str, Any]]]) -> bool:
    steps = [(n, a) for n, a in calls if n != "wait_for_window"]
    if "plan" in expected:
        wanted = [set(s.split("|")) for s in expected["plan"]]
        return len(steps) == len(wanted) and all(
            n in w for (n, _), w in zip(steps, wanted, strict=True)
        )
    if len(steps) != 1 or steps[0][0] not in set(expected["tool"].split("|")):
        return False
    return all(_same(v, steps[0][1].get(k)) for k, v in expected.get("args", {}).items())


def judge(expected: dict[str, Any], seen: Observed) -> Verdict:
    """Veredicto de una frase de la batería según lo esperado (formato de `guion.Item`)."""
    tipo = expected.get("tipo")
    if tipo == "ignorar":
        return Verdict.SIN_DEBER if (seen.calls or seen.reply) else Verdict.BIEN
    if not seen.activated:
        return Verdict.NO_ACTIVO
    if tipo is not None:
        if seen.calls:
            return Verdict.MAL
        if tipo == "preguntar":
            return Verdict.PREGUNTO if _asks(seen.reply) else Verdict.NADA
        if tipo == "respuesta":
            useful = seen.reply and "aun no se" not in normalize(seen.reply)
            return Verdict.BIEN if useful else Verdict.NADA
        return Verdict.BIEN  # no_sabe: no actuar es lo correcto
    if seen.calls:
        return Verdict.BIEN if _calls_match(expected, seen.calls) else Verdict.MAL
    return Verdict.PREGUNTO if _asks(seen.reply) else Verdict.NADA
