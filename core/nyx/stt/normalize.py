"""Limpieza de la transcripción (SPEC sección 5).

- Descarta las «alucinaciones» típicas de Whisper con silencio o ruido.
- Quita «Nyx» (y cómo suele transcribirse) del principio.
- Comprueba si la palabra de activación aparece de verdad (segunda verificación).
- Comprueba si la palabra de activación aparece de verdad (segunda verificación).
- Horas: «a las diez cincuenta» / «a las 10 y 50» → «a las 10:50».
"""

from __future__ import annotations

import re
import unicodedata

# Frases que Whisper inventa con audio vacío (entrenado con subtítulos de vídeos).
HALLUCINATIONS = (
    "subtitulos realizados por la comunidad de amara.org",
    "subtitulos por la comunidad de amara.org",
    "gracias por ver el video",
    "gracias por ver",
    "suscribete",
    "gracias",
    "musica",
    "aplausos",
)

# Cómo transcribe Whisper «Nyx» (visto en pruebas reales: «Nix», «Nyx», «NYAX»…).
WAKE_VARIANTS = frozenset({"nyx", "nix", "nics", "niks", "nicks", "nyks", "nyax", "nik", "nick"})
_WAKE = re.compile(
    rf"^\s*(?:oye\s*,?\s*)?(?:{'|'.join(sorted(WAKE_VARIANTS))})\b[\s,.:;-]*",
    re.IGNORECASE,
)
_WORD = re.compile(r"\w+")


def has_wake_word(text: str, *, first_words: int | None = None) -> bool:
    """¿Aparece «Nyx» en el texto? Con `first_words`, solo entre las primeras palabras."""
    words = [w.lower() for w in _WORD.findall(text)]
    if first_words is not None:
        words = words[:first_words]
    return any(w in WAKE_VARIANTS for w in words)


_UNITS = {
    "cero": 0,
    "un": 1,
    "una": 1,
    "uno": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
    "diez": 10,
    "once": 11,
    "doce": 12,
    "trece": 13,
    "catorce": 14,
    "quince": 15,
    "dieciseis": 16,
    "diecisiete": 17,
    "dieciocho": 18,
    "diecinueve": 19,
    "veinte": 20,
    "veintiun": 21,
    "veintiuno": 21,
    "veintiuna": 21,
    "veintidos": 22,
    "veintitres": 23,
    "veinticuatro": 24,
    "veinticinco": 25,
    "veintiseis": 26,
    "veintisiete": 27,
    "veintiocho": 28,
    "veintinueve": 29,
}
_TENS = {"treinta": 30, "cuarenta": 40, "cincuenta": 50}


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _number_words() -> dict[str, int]:
    words = dict(_UNITS)
    for tens_word, tens in _TENS.items():
        words[tens_word] = tens
        for unit_word, unit in _UNITS.items():
            if 1 <= unit <= 9:
                words[f"{tens_word} y {unit_word}"] = tens + unit
    return words


NUMBER_WORDS = _number_words()
_NUM = "|".join(sorted((re.escape(w) for w in NUMBER_WORDS), key=len, reverse=True))
_HOUR = rf"(\d{{1,2}}|{_NUM})"
_MIN = rf"(\d{{1,2}}|{_NUM}|media|cuarto)"

# «a las 10 y 50», «a las diez cincuenta», «a la una y media», «a las once menos cuarto»
_TIME = re.compile(
    rf"\b(a las|a la)\s+{_HOUR}(?:\s+(y|menos))?\s+{_MIN}\b",
    re.IGNORECASE,
)


def _value(token: str) -> int | None:
    token = token.lower()
    if token.isdigit():
        return int(token)
    if token == "media":
        return 30
    if token == "cuarto":
        return 15
    return NUMBER_WORDS.get(token)


def _time_sub(m: re.Match[str]) -> str:
    prefix, hour_tok, joiner, minute_tok = m.group(1), m.group(2), m.group(3), m.group(4)
    hour, minute = _value(hour_tok), _value(minute_tok)
    if hour is None or minute is None or not 0 <= hour <= 24 or not 0 <= minute <= 59:
        return m.group(0)
    if joiner and joiner.lower() == "menos":
        hour, minute = (hour - 1) % 24, 60 - minute
    elif joiner is None and minute_tok.lower() in ("media", "cuarto"):
        return m.group(0)  # «a las diez cuarto» no es una hora
    elif joiner is None and minute < 10 and not minute_tok.isdigit():
        return m.group(0)  # «a las tres dos…» probablemente no es una hora
    return f"{prefix} {hour}:{minute:02d}"


def normalize_times(text: str) -> str:
    # Las palabras de número se comparan sin tildes («dieciséis» = «dieciseis»).
    plain = _strip_accents(text)
    if plain == text or len(plain) != len(text):
        return _TIME.sub(_time_sub, text)
    # Sustituye sobre el texto sin tildes solo en los tramos que cambian.
    out, last = [], 0
    for m in _TIME.finditer(plain):
        out.append(text[last : m.start()])
        out.append(_time_sub(m))
        last = m.end()
    out.append(text[last:])
    return "".join(out)


def is_hallucination(text: str) -> bool:
    key = _strip_accents(text).lower().strip(" .,!¡?¿…-\"'()[]*")
    return not key or key in HALLUCINATIONS


def strip_wake_word(text: str) -> str:
    return _WAKE.sub("", text, count=1)


def normalize(text: str) -> str:
    """Texto listo para el cerebro, o "" si no hay nada útil."""
    text = " ".join(text.split())
    if is_hallucination(text):
        return ""
    text = strip_wake_word(text).strip()
    if is_hallucination(text):
        return ""
    text = normalize_times(text)
    # Mayúscula en la primera letra, aunque vaya detrás de «¿» o «¡».
    first = next(i for i, c in enumerate(text) if c.isalnum())
    return text[:first] + text[first].upper() + text[first + 1 :]
