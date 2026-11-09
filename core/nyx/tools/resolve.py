"""Resolver un nombre dicho por el usuario a una entrada de la caché, o explicar por qué no."""

from __future__ import annotations

from nyx.index.model import Kind
from nyx.index.service import Match, SystemIndex
from nyx.tools.base import ToolResult

# Las herramientas son algo más permisivas que el router: si las llama el LLM es porque ya
# ha entendido la intención; basta una coincidencia buena y clara.
TOOL_MIN_SCORE = 80.0
TIE_MARGIN = 3.0


def pick(index: SystemIndex, name: str, kinds: set[Kind], what: str = "") -> Match | ToolResult:
    matches = index.resolve(name, kinds)
    if confident := index.confident(matches):
        return confident
    if matches and matches[0].score >= TOOL_MIN_SCORE:
        if len(matches) == 1 or matches[0].score - matches[1].score >= TIE_MARGIN:
            return matches[0]
        a, b = matches[0].entry.name, matches[1].entry.name
        return ToolResult.fail(f"¿{a} o {b}?", "dime cuál")
    label = f"{what} «{name}»" if what else f"«{name}»"
    suggestion = f"¿quizá {matches[0].entry.name}?" if matches else None
    return ToolResult.fail(f"No encuentro {label}", suggestion)
