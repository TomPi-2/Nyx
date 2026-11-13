"""Criterio común de los paneles de respuesta (0.6, tarea 6.23).

Todo panel pasa por `tidy` antes de mostrarse (respuestas del LLM, herramientas, frases fijas,
alarmas y el resumen de la partida):

- Las dos líneas empiezan en mayúscula.
- Punto final solo si la línea es una frase («Te quedan 120 GB libres en C:.»), nunca en una
  etiqueta («40 %», «Bohemian Rhapsody», «Queen · Spotify»): así lo pide la ortografía (RAE: los
  títulos, rótulos y etiquetas no llevan punto). Decidido con el usuario el 2026-11-13.
- La línea pequeña se quita si no aporta: relleno («respuesta», «dato»…) o lo mismo que la
  grande.
- Si la grande es una palabra que no dice nada («Sí», «Claro», «Hecho»…) y se sabe lo que se
  va a decir, la grande es la primera frase de la voz («Sí, mañana va a llover.»).
"""

from __future__ import annotations

import re

from nyx.brain.reply import first_sentence
from nyx.index.aliases import normalize

# Líneas pequeñas que no dicen nada.
FILLER = frozenset(
    {
        "respuesta", "dato", "datos", "informacion", "info", "resultado", "contexto", "nyx",
        "prueba", "vale", "ok", "hecho", "listo", "texto", "mensaje", "nota", "aviso",
    }
)  # fmt: skip

# Grandes de una palabra que necesitan el detalle de la voz.
BARE = frozenset(
    {
        "si", "no", "claro", "vale", "hola", "bien", "hecho", "listo", "entendido", "perfecto",
        "genial", "gracias", "nada", "ok", "okay", "adios", "buenas", "exacto", "correcto",
        "cierto", "depende", "quizas", "tal vez", "ninguno", "ninguna", "nunca", "siempre",
    }
)  # fmt: skip

# Formas verbales frecuentes: con una de ellas (y varias palabras) la línea es una frase.
_VERBS = frozenset(
    {
        "es", "son", "era", "fue", "esta", "estan", "estoy", "estas", "hay", "habra", "tienes",
        "tiene", "tengo", "tienen", "queda", "quedan", "va", "van", "voy", "vas", "hace", "hara",
        "suena", "puedes", "puede", "puedo", "he", "has", "ha", "han", "se", "llama", "lleva",
        "dice", "sale", "sirve", "significa", "quiere", "necesitas", "falta", "faltan", "sera",
        "seran", "estara", "llueve", "llovera", "hizo", "escribio", "pinto", "nacio", "murio",
        "vive", "mide", "pesa", "cuesta", "tarda", "sabes", "sigue", "siguen", "aguanta",
    }
)  # fmt: skip
# Solo terminaciones que casi nunca son de sustantivos («-ía» o «-era» no: batería, primera).
_VERB_ENDINGS = ("aba", "aban", "amos", "aron", "ieron", "ando", "iendo")

_STARTS = re.compile(r"^([¿¡«\"'(]*)(\w)")
_END = (".", "!", "?", "…", ":", ";")


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", normalize(text))


def is_sentence(text: str) -> bool:
    """¿Es una frase (lleva verbo y varias palabras) y no una etiqueta?"""
    if " · " in text:
        return False  # «Queen · Spotify», «batería · enchufado»: etiquetas juntas
    words = _words(text)
    if len(words) < 3:
        return False
    return any(w in _VERBS or (len(w) > 4 and w.endswith(_VERB_ENDINGS)) for w in words)


def capitalize(text: str) -> str:
    """Mayúscula inicial (también tras «¿», «¡» o «"»), sin tocar marcas como «iPhone»."""
    m = _STARTS.match(text)
    if m is None:
        return text
    first_word = re.match(r"\w+", text[m.start(2) :])
    if first_word and any(c.isupper() for c in first_word.group()[1:]):
        return text  # «iPhone», «macOS»
    return text[: m.start(2)] + m.group(2).upper() + text[m.end(2) :]


def finish(text: str) -> str:
    """Punto final si es una frase y no lleva ya un signo de cierre (tras «»» también:
    «Suena «Imagine».»)."""
    text = text.rstrip()
    drive = re.search(r"\b[A-Z]:$", text) is not None  # «en C:»: los dos puntos son del disco
    if text and is_sentence(text) and (drive or not text.endswith(_END)):
        return text + "."
    return text


def _adds_nothing(secondary: str, display: str) -> bool:
    norm = " ".join(_words(secondary))
    if not norm or norm in FILLER:
        return True
    big, small = set(_words(display)), set(_words(secondary))
    return bool(small) and small <= big


def tidy(display: str, secondary: str = "", spoken: str = "") -> tuple[str, str]:
    """El panel listo para enseñar: (línea grande, línea pequeña o «»)."""
    display, secondary = display.strip(), (secondary or "").strip()
    if spoken and " ".join(_words(display)) in BARE:
        first = first_sentence(spoken.strip())
        if len(_words(first)) > len(_words(display)):
            display = first
            if secondary.startswith(first):  # escrito: debajo iba la respuesta entera
                secondary = secondary[len(first) :].strip()
    if secondary and _adds_nothing(secondary, display):
        secondary = ""
    return finish(capitalize(display)), finish(capitalize(secondary)) if secondary else ""
