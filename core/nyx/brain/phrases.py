"""Frases fijas de Nyx con variantes para no repetir siempre lo mismo (0.6, tarea 6.15).

Errores, «hecho» y «no te he entendido» viven en este archivo con 2–3 variantes cada uno;
al elegir una, se evita repetir la última usada de ese grupo.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from nyx.brain.base import LLMErrorKind


@dataclass(frozen=True, slots=True)
class Phrase:
    display: str
    secondary: str = ""
    spoken: str = ""


PHRASES: dict[str, tuple[Phrase, ...]] = {
    "done": (
        Phrase("Hecho", "", "Hecho."),
        Phrase("Listo", "", "Listo."),
        Phrase("Ya está", "", "Ya está."),
    ),
    "not_understood": (
        Phrase("No he entendido bien qué hacer", "¿lo repites?", "No he entendido bien qué hacer."),
        Phrase("No te he entendido bien", "¿me lo repites?", "No te he entendido bien."),
        Phrase(
            "No me ha quedado claro qué hacer",
            "¿lo dices otra vez?",
            "No me ha quedado claro qué hacer.",
        ),
    ),
    "garbled": (
        Phrase("No he podido hacerlo", "¿me lo pides de otra forma?", "No he podido hacerlo."),
        Phrase("No me ha salido bien", "¿lo intentas de otra manera?", "No me ha salido bien."),
        Phrase("Me he liado con eso", "¿me lo pides distinto?", "Me he liado con eso."),
    ),
    "error_stt": (
        Phrase("No he podido oírte bien", "fallo al transcribir"),
        Phrase("No te he entendido bien", "fallo al transcribir"),
        Phrase("No ha quedado claro", "vuelve a decirlo"),
    ),
    "error_unavailable": (
        Phrase(
            "Sin conexión con Ollama",
            "no he podido abrirlo",
            "No puedo conectar con el modelo de lenguaje.",
        ),
        Phrase("Ollama no responde", "prueba a abrirlo", "El modelo de lenguaje no responde."),
        Phrase("No llego a Ollama", "revisa que esté abierto", "No consigo conectar con Ollama."),
    ),
    "error_model_missing": (
        Phrase("Falta el modelo", "descárgalo con ollama pull", "Falta el modelo de lenguaje."),
        Phrase(
            "No encuentro el modelo",
            "revísalo en Ajustes → Cerebro",
            "No tengo descargado ese modelo.",
        ),
        Phrase(
            "Modelo no disponible",
            "descárgalo para usarlo",
            "Ese modelo de lenguaje no está instalado.",
        ),
    ),
    "error_timeout": (
        Phrase("Me he atascado", "¿lo repites?", "Me he atascado, ¿lo repites?"),
        Phrase(
            "He tardado demasiado", "¿me lo repites?", "Se me ha acabado el tiempo, ¿lo repites?"
        ),
        Phrase(
            "No he llegado a tiempo",
            "inténtalo otra vez",
            "He tardado más de la cuenta, ¿lo repites?",
        ),
    ),
    "error_other": (
        Phrase("Algo ha fallado", "inténtalo otra vez", "Algo ha fallado."),
        Phrase("Ha habido un error", "prueba otra vez", "Algo ha salido mal, inténtalo otra vez."),
        Phrase(
            "No he podido completarlo",
            "inténtalo de nuevo",
            "Algo ha fallado al procesarlo.",
        ),
    ),
}

LLM_ERROR_KEY: dict[LLMErrorKind, str] = {
    LLMErrorKind.UNAVAILABLE: "error_unavailable",
    LLMErrorKind.MODEL_MISSING: "error_model_missing",
    LLMErrorKind.TIMEOUT: "error_timeout",
    LLMErrorKind.OTHER: "error_other",
}


class PhraseBook:
    """Elige variantes al azar sin repetir la última de cada clave."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()
        self._last: dict[str, int] = {}

    def pick(self, key: str) -> Phrase:
        options = PHRASES[key]
        if len(options) <= 1:
            return options[0]
        last = self._last.get(key)
        indices = [i for i in range(len(options)) if i != last]
        chosen = self._rng.choice(indices)
        self._last[key] = chosen
        return options[chosen]

    def llm_error(self, kind: LLMErrorKind) -> Phrase:
        return self.pick(LLM_ERROR_KEY[kind])


_DEFAULT = PhraseBook()


def pick(key: str) -> Phrase:
    return _DEFAULT.pick(key)


def llm_error(kind: LLMErrorKind) -> Phrase:
    return _DEFAULT.llm_error(kind)
