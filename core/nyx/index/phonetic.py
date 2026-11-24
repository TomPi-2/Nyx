"""Corrector por sonido en español (Cerebro 2, C1.4; paso 2, 2026-11-24).

Whisper escribe como suena: «espotifai», «fortnait», «estim», «balorant», «dis cord»… y la
búsqueda difusa (letra a letra) no siempre lo encuentra. Aquí cada nombre se pasa a una clave
de cómo se pronuncia en español, tanto lo que oyó Whisper como los nombres del equipo (muchos
en inglés), y se comparan esas claves.

No sustituye a la búsqueda normal: solo se usa cuando esa no encuentra nada claro.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from rapidfuzz import fuzz

from nyx.index.aliases import normalize

#: Parecido mínimo entre claves para proponer un nombre, y ventaja sobre el segundo.
MIN_SCORE = 82.0
MARGIN = 6.0

# Inglés escrito → cómo lo dice un hispanohablante (solo en los nombres del equipo).
_ENGLISH = (
    (re.compile(r"i([bcdfgklmnprstvz])e\b"), r"ai\1"),  # fortnite → fortnait, like → laik
    (re.compile(r"a([bcdfgklmnprstvz])es?\b"), r"ei\1s"),  # games → geims
    (re.compile(r"(?<=[bcdfgklmnprstvz])y\b"), "ai"),  # spotify → spotifai
    (re.compile(r"ee|ea"), "i"),  # steam → stim, league → ligue
    (re.compile(r"oo"), "u"),
    (re.compile(r"ou"), "au"),  # discount → diskaunt
)
# Español y lo que comparten los dos: letras que suenan igual → una sola.
_SOUNDS = (
    (re.compile(r"ch"), "C"),  # se guarda aparte para que la «h» muda no la rompa
    (re.compile(r"sh"), "C"),
    (re.compile(r"ph"), "f"),
    (re.compile(r"th"), "t"),
    (re.compile(r"ck"), "k"),
    (re.compile(r"qu(?=[ei])"), "k"),
    (re.compile(r"gu(?=[ei])"), "G"),  # «gue», «gui»: g fuerte (se guarda aparte)
    (re.compile(r"g(?=[ei])"), "j"),
    (re.compile(r"G"), "g"),
    (re.compile(r"c(?=[ei])"), "s"),
    (re.compile(r"[cq]"), "k"),
    (re.compile(r"z"), "s"),
    (re.compile(r"x"), "ks"),
    (re.compile(r"ll"), "y"),
    (re.compile(r"y(?=[^aeiou]|$)"), "i"),
    (re.compile(r"w"), "u"),
    (re.compile(r"v"), "b"),
    (re.compile(r"h"), ""),
    (re.compile(r"^e(?=s[^aeiou])"), ""),  # «estim», «espotifai»: la «e» de apoyo
    (re.compile(r"d$"), ""),  # «discor(d)», «Madri(d)»: la «d» final se pierde
    (re.compile(r"(.)\1+"), r"\1"),  # letras dobles
)


def _word_key(word: str, *, english: bool) -> str:
    if english:
        for pattern, repl in _ENGLISH:
            word = pattern.sub(repl, word)
    for pattern, repl in _SOUNDS:
        word = pattern.sub(repl, word)
    return word


# Letras dichas por su nombre: «o be ese» → OBS, «opera ge equis» → Opera GX.
_LETTERS = {
    "a": "a", "be": "b", "ce": "c", "de": "d", "e": "e", "efe": "f", "ge": "g", "hache": "h",
    "i": "i", "jota": "j", "ka": "k", "ele": "l", "eme": "m", "ene": "n", "o": "o", "pe": "p",
    "cu": "q", "erre": "r", "ese": "s", "te": "t", "u": "u", "uve": "v", "equis": "x",
    "zeta": "z",
}  # fmt: skip


def spelled(words: list[str]) -> list[str]:
    """Junta en una palabra las letras dichas una a una (dos o más seguidas)."""
    out: list[str] = []
    run: list[str] = []
    for w in [*words, None]:
        if w is not None and w in _LETTERS:
            run.append(w)
            continue
        if len(run) >= 2:
            out.append("".join(_LETTERS[r] for r in run))
        else:
            out += run
        run = []
        if w is not None:
            out.append(w)
    return out


def key(text: str, *, english: bool = False) -> str:
    """La clave de cómo suena `text`, sin espacios («dis cord» y «discord» suenan igual)."""
    words = normalize(text).split()
    if not english:
        words = spelled(words)
    return "".join(_word_key(w, english=english) for w in words)


def keys(name: str) -> set[str]:
    """Las claves de un nombre del equipo: leído en español y leído como inglés."""
    return {key(name), key(name, english=True)}


@dataclass(frozen=True, slots=True)
class SoundMatch:
    name: str
    alias: str
    score: float
    exact: bool  # suena exactamente igual


def best_by_sound(heard: str, candidates: Iterable[tuple[str, str]]) -> SoundMatch | None:
    """El nombre que mejor suena como `heard`, entre (nombre, alias). None si ninguno se parece
    lo bastante o si dos nombres distintos se parecen casi igual (mejor preguntar)."""
    target = key(heard)
    if len(target) < 3:
        return None
    best: dict[str, SoundMatch] = {}
    for name, alias in candidates:
        for k in keys(alias):
            if not k:
                continue
            score = float(fuzz.ratio(target, k))
            if score > (best[name].score if name in best else -1.0):
                best[name] = SoundMatch(name, alias, score, k == target)
    ranked = sorted(best.values(), key=lambda m: m.score, reverse=True)
    if not ranked or ranked[0].score < MIN_SCORE:
        return None
    # Dos que suenan casi igual: solo vale si el primero suena exacto y el otro no.
    close = len(ranked) > 1 and ranked[0].score - ranked[1].score < MARGIN
    if close and (not ranked[0].exact or ranked[1].exact):
        return None
    return ranked[0]
