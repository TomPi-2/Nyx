"""Códigos de error que ve el usuario (docs/CODIGOS-DE-ERROR.md).

Cuando algo falla y se le enseña al usuario, va con un código («D-201») para que pueda buscar
en la web qué ha pasado y qué hacer (`tepnyx.com/nyx/errores#D-201`). La interfaz lo saca del
principio del texto (`coded`), así que basta con que el mensaje empiece por él.
"""

from __future__ import annotations

import re

ERRORS_URL = "https://tepnyx.com/nyx/errores"

# Descargas del primer arranque.
DOWNLOAD_FAILED = "D-201"
DOWNLOAD_HASH = "D-202"
OLLAMA_INSTALL = "D-210"
OLLAMA_START = "D-211"
BRAIN_PULL = "D-220"
BRAIN_JOIN = "D-221"

# Núcleo.
LLM_START = "N-410"
LLM_CPU = "N-411"

CODE = re.compile(r"^([IDAN]-\d{3})\b")


def coded(code: str, text: str) -> str:
    """El texto para el usuario con su código delante: «D-201 · No he podido descargar…»."""
    return f"{code} · {text}"


def code_of(text: str | None) -> str | None:
    match = CODE.match(text or "")
    return match.group(1) if match else None
