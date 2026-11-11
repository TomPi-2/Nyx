"""Filtro de salida: Nyx nunca dice ni muestra código, JSON ni llamadas a herramientas.

A veces el modelo escribe sus acciones como texto (imitando la memoria corta,
«[acciones] app_action({…})») y el intérprete de `textcalls` no las reconoce. Sin este
filtro, Nyx las leería en voz alta (ERRORES.md, 2026-11-11).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

GARBLED_REPLY = ("No he podido hacerlo", "¿me lo pides de otra forma?")

_CODE = re.compile(
    r"\{\s*\"[^\"]{1,40}\"\s*:"  # JSON: {"app": …
    r"|\b[A-Za-z]+_[A-Za-z_]+\s*\("  # app_action(
    r"|\b[A-Za-z]{3,}\s*\(\s*[{\[\"']"  # appaction({ · open(" …
    r"|</?tool_?call>"
    r"|^\s*\[acciones\]"
)


def looks_like_code(text: str) -> bool:
    """¿Parece código o una llamada a herramienta en vez de una frase para una persona?"""
    return bool(_CODE.search(text))


def tool_keys(names: Iterable[str]) -> frozenset[str]:
    """«list_alarms» → «listalarms»: así se reconoce con o sin guion bajo."""
    return frozenset(n.replace("_", "").lower() for n in names)


def mentions_tool(text: str, keys: frozenset[str]) -> bool:
    """¿Lleva el nombre interno de una herramienta? («[set_alarm | …]», «listalarms, …»)."""
    words = re.findall(r"[A-Za-z_]{4,}", text)
    return any(w.replace("_", "").lower() in keys for w in words)
