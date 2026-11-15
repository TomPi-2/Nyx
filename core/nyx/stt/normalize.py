"""Limpieza de la transcripción (SPEC sección 5).

- Descarta las «alucinaciones» típicas de Whisper con silencio o ruido.
- Quita «Nyx» (y cómo suele transcribirse) del principio.
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
    rf"^\s*[-–—\"'«]*\s*[¿¡]?\s*(?:oye\s*,?\s*)?(?:{'|'.join(sorted(WAKE_VARIANTS))})\b"
    r"[\s,.:;!?-]*",
    re.IGNORECASE,
)
# «Esto está roto. Nyx, ¿qué día es hoy?»: el nombre tras un punto y con una pausa detrás. Lo
# de antes no era para Nyx (ERRORES.md, 2026-11-14).
_WAKE_MID = re.compile(
    rf"(?<=[.!?…])\s*[¿¡]?\s*(?:{'|'.join(sorted(WAKE_VARIANTS))})\s*[,.:;!?]+\s*",
    re.IGNORECASE,
)
# Whisper a veces oye «¿Mix?» por «¿Nyx?». Solo al principio y con puntuación detrás; nunca
# cuenta como confirmación en `has_wake_word` para no activar con «mix» en una conversación.
_WAKE_MIX = re.compile(
    r"^\s*[¿¡]?\s*(?:oye\s*,?\s*)?mix\s*[,.:;!?]+[\s,.:;!?-]*",
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
    stripped = _WAKE.sub("", text, count=1)
    if stripped == text:
        stripped = _WAKE_MIX.sub("", text, count=1)
    # «Esto está roto. Nyx, ¿qué día es hoy?»: se atiende lo dicho tras el último «Nyx».
    found = list(_WAKE_MID.finditer(stripped))
    last = found[-1] if found else None
    if last is not None and _WORD.search(stripped[last.end() :]):
        stripped = stripped[last.end() :]
    return stripped


# Letras que no existen en español. Con música o ruido, Whisper a veces «oye» islandés o
# alemán aunque se le pida español (ERRORES.md, 2026-11-14: «Þó er langsði nýx í»). Las de
# _RARE salen en nombres propios («Motörhead», «Björk»): una sola palabra no basta.
_ALIEN = frozenset("þðæøõßãåœ")
_RARE = frozenset("äëïöÿâêîôûàèìòùýčřšžł")


def looks_foreign(text: str) -> bool:
    """¿La transcripción está en otro idioma (y por tanto mal oída)?"""
    words = [w.lower() for w in _WORD.findall(text)]
    if any(_ALIEN.intersection(w) for w in words):
        return True
    return sum(1 for w in words if _RARE.intersection(w)) >= 2


def addressed_by_name(text: str) -> bool:
    """¿Se dirige a Nyx por su nombre («Nix, ¿quién es tu creador?»)? Entonces, en la ventana
    de seguimiento, no hace falta preguntar al modelo si iba para Nyx."""
    return _WAKE.match(text) is not None or _WAKE_MID.search(text) is not None


_SENTENCE = re.compile(r"(?<=[.!?…])\s+")


def _sentence_key(text: str) -> str:
    return " ".join(_WORD.findall(_strip_accents(text).lower()))


def _drop_repeats(text: str) -> str:
    """«Siguiente. Siguiente.» o «Más pequeño más pequeño» → una vez: Whisper repite lo dicho
    cuando la frase es corta (registros del 2026-11-14 y 15)."""
    parts = [p for p in _SENTENCE.split(text) if _sentence_key(p)]
    if len(parts) > 1 and len({_sentence_key(p) for p in parts}) == 1:
        return parts[0].strip()
    words = text.split()
    half = len(words) // 2
    if len(words) >= 2 and len(words) % 2 == 0:
        first, second = " ".join(words[:half]), " ".join(words[half:])
        if _sentence_key(first) and _sentence_key(first) == _sentence_key(second):
            return first.strip().rstrip(",")
    return text


def _drop_trailing_hallucination(text: str) -> str:
    """«Pasa la canción. Gracias.»: el «Gracias.» del final suele ser invento de Whisper."""
    parts = _SENTENCE.split(text)
    if len(parts) > 1 and is_hallucination(parts[-1]):
        return " ".join(parts[:-1]).strip()
    return text


def normalize(text: str) -> str:
    """Texto listo para el cerebro, o "" si no hay nada útil."""
    text = " ".join(text.split())
    if is_hallucination(text):
        return ""
    text = strip_wake_word(text).strip()
    # «Nix. Nix. Pasa la canción.»: el nombre dos veces (registros del 2026-11-15).
    for _ in range(2):
        again = strip_wake_word(text).strip()
        if again == text:
            break
        text = again
    text = _drop_trailing_hallucination(_drop_repeats(text))
    if is_hallucination(text):
        return ""
    text = normalize_times(text)
    # Mayúscula en la primera letra, aunque vaya detrás de «¿» o «¡».
    first = next((i for i, c in enumerate(text) if c.isalnum()), None)
    if first is None:
        return text
    return text[:first] + text[first].upper() + text[first + 1 :]


#: Parte de lo oído que tiene que estar en lo que dice Nyx para tomarlo por su propia voz.
ECHO_SHARE = 0.6


def _plain_words(text: str) -> list[str]:
    plain = _strip_accents(text.lower())
    return ["nyx" if w in WAKE_VARIANTS else w for w in _WORD.findall(plain)]


def is_echo(heard: str, spoken: str) -> bool:
    """¿Lo que ha oído whisper es la propia voz de Nyx saliendo por los altavoces?

    Sin cancelación de eco, cuando Nyx dice su nombre («¡Hola! Soy Nyx») el micrófono la oye y
    se activaba sola (ERRORES.md, 2026-11-14). Es eco si casi todo lo oído está en lo que está
    diciendo; «Nyx» suelto solo si ella también lo dice.
    """
    said = set(_plain_words(spoken))
    words = _plain_words(heard)
    if not words or not said:
        return False
    others = [w for w in words if w != "nyx"]
    if not others:
        return "nyx" in said
    hits = sum(1 for w in others if w in said)
    return hits >= ECHO_SHARE * len(others)
