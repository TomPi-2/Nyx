"""Palabras de activación personalizadas (SPEC sección 4, fase 4d).

- `validate`: al menos 2 sílabas, todas las palabras en el vocabulario de Vosk (si no, Vosk no
  puede oírlas) y aviso si se parece a palabras de todos los días (saltaría sin querer).
- `WakePhrase`: lo que whisper debe oír para confirmar la activación y lo que se quita del
  principio de la frase («Oye Lumen, abre Spotify» → «abre Spotify»). «Nyx» es una más.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from nyx.index.aliases import normalize
from nyx.stt.normalize import has_wake_word, strip_wake_word

_VOWELS = re.compile(r"[aeiouáéíóúü]+|y(?![aeiouáéíóú])", re.IGNORECASE)
# Palabras muy frecuentes: una palabra de activación parecida saltaría a cada rato.
_COMMON_WORDS = (
    "hola", "oye", "vale", "venga", "bueno", "pues", "mira", "dime", "nada", "nunca", "ahora",
    "luego", "claro", "gracias", "perdona", "casa", "cosa", "coche", "mesa", "luna", "sol",
    "mano", "madre", "padre", "hermano", "amigo", "amiga", "trabajo", "juego", "partida",
    "nota", "tiempo", "hora", "mañana", "tarde", "noche", "día", "semana", "dinero", "comida",
    "agua", "música", "canción", "vídeo", "ordenador", "móvil", "teléfono", "pantalla",
    "ventana", "puerta", "perro", "gato", "chico", "chica", "señor", "señora", "siempre",
    "también", "porque", "cuando", "donde", "como", "quien", "cual", "mucho", "poco", "todo",
    "nadie", "alguien",
)  # fmt: skip
COMMON = frozenset(_COMMON_WORDS)
SIMILAR = 85  # % de parecido a partir del cual se avisa


def syllables(text: str) -> int:
    """Sílabas aproximadas en español: grupos de vocales (diptongos = una)."""
    return sum(len(_VOWELS.findall(word)) for word in text.split())


@dataclass
class Validation:
    problems: list[str] = field(default_factory=list)  # impiden usarla
    warnings: list[str] = field(default_factory=list)  # se puede, pero mejor otra

    @property
    def ok(self) -> bool:
        return not self.problems


def validate(phrase: str, in_vocabulary: Callable[[str], bool] | None = None) -> Validation:
    result = Validation()
    words = normalize(phrase).split()
    if not words:
        result.problems.append("está vacía")
        return result
    if syllables(phrase) < 2:
        result.problems.append("necesita al menos 2 sílabas (prueba «Oye …»)")
    if in_vocabulary is not None:
        unknown = [w for w in words if not in_vocabulary(w)]
        if unknown:
            result.problems.append(f"el reconocedor no conoce: {', '.join(unknown)}")
    if len(words) == 1:
        close = [c for c in COMMON if fuzz.ratio(words[0], normalize(c)) >= SIMILAR]
        if close:
            result.warnings.append(f"se parece a palabras comunes ({', '.join(sorted(close))})")
    return result


def vosk_vocabulary(model: object) -> Callable[[str], bool]:
    """¿Conoce el modelo de Vosk esta palabra? (función C vosk_model_find_word)."""
    import vosk

    handle = getattr(model, "_handle")  # noqa: B009

    def known(word: str, _model: object = model) -> bool:
        # `_model` mantiene vivo el modelo: si se liberase, el puntero quedaría colgando.
        return int(vosk._c.vosk_model_find_word(handle, word.encode())) >= 0

    return known


@dataclass(frozen=True)
class WakePhrase:
    """La palabra de activación vista desde el texto transcrito."""

    words: tuple[str, ...] = ()  # vacío = «Nyx» (con sus variantes: nix, niks…)

    @classmethod
    def custom(cls, phrase: str) -> WakePhrase:
        return cls(tuple(normalize(phrase).split()))

    @property
    def is_nyx(self) -> bool:
        return not self.words

    def heard(self, text: str, *, first_words: int | None = None) -> bool:
        if self.is_nyx:
            return has_wake_word(text, first_words=first_words)
        said = normalize(text).split()
        limit = len(said) if first_words is None else min(len(said), first_words + len(self.words))
        n = len(self.words)
        return any(
            all(fuzz.ratio(a, b) >= 80 for a, b in zip(said[i : i + n], self.words, strict=True))
            for i in range(0, max(0, limit - n + 1))
        )

    def without(self, text: str) -> str:
        """Quita la palabra del principio de la frase."""
        if self.is_nyx:
            return strip_wake_word(text)
        tokens = text.split()
        said = [normalize(t) for t in tokens]
        n = len(self.words)
        if len(said) >= n and all(
            fuzz.ratio(a, b) >= 80 for a, b in zip(said[:n], self.words, strict=True)
        ):
            return " ".join(tokens[n:]).lstrip(" ,.:;-")
        return text
