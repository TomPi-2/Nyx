"""nyx_info: lo que Nyx sabe de sí misma (verde, consulta).

«¿Qué puedes hacer?», «explícame tu modo partida», «¿qué hay en tus ajustes de voz?». Antes,
«explícame tu configuración del modo partida» abría Ajustes en vez de explicarla (ERRORES.md,
2026-11-11). El texto está en `nyx/brain/knowledge/nyx.md`, por apartados `##`.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from pydantic import Field

from nyx.index.aliases import normalize
from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult

KNOWLEDGE = Path(__file__).resolve().parents[1] / "brain" / "knowledge" / "nyx.md"

# Palabras de la pregunta → apartado (además del propio título).
_HINTS = {
    "que se hacer": ("puedes", "sabes", "haces", "hacer", "funciones", "capaz"),
    "modo partida": ("partida", "juego", "jugar", "juegas", "gaming"),
    "ajustes": ("ajustes", "configuracion", "opciones", "apariencia", "voz", "cerebro", "cache"),
    "atajos de teclado": ("atajo", "atajos", "teclado", "teclas"),
    "lo que nunca hago": ("nunca", "prohibido", "no haces", "no puedes"),
    "privacidad": ("privacidad", "datos", "graba", "grabas", "internet", "espias"),
    "quien soy": ("quien", "eres", "llamas", "nyx"),
}


@cache
def sections() -> dict[str, str]:
    """{título normalizado: texto} de cada apartado `##`."""
    out: dict[str, str] = {}
    title = ""
    lines: list[str] = []
    for line in KNOWLEDGE.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            if title:
                out[title] = "\n".join(lines).strip()
            title, lines = normalize(line[3:]), []
        elif title:
            lines.append(line)
    if title:
        out[title] = "\n".join(lines).strip()
    return out


def find(topic: str) -> str:
    """El apartado que mejor encaja con `topic` (vacío: el resumen de qué sé hacer)."""
    known = sections()
    want = normalize(topic)
    if not want:
        return known["que se hacer"]
    for title, text in known.items():
        if title in want or want in title:
            return text
    scores = {title: sum(1 for w in _HINTS.get(title, ()) if w in want) for title in known}
    best = max(scores, key=lambda t: scores[t])
    return known[best] if scores[best] else known["que se hacer"]


class NyxInfoParams(Params):
    topic: str = Field(
        default="",
        max_length=100,
        description="De qué: qué sabes hacer, modo partida, ajustes, atajos, lo que nunca "
        "haces, privacidad, quién eres. Vacío = qué sabes hacer",
    )


class NyxInfo(Tool[NyxInfoParams]):
    name = "nyx_info"
    description = (
        "Explica cosas sobre ti, Nyx: qué sabes hacer, cómo funcionas en partida, qué hay en "
        "tus ajustes, tus atajos y lo que nunca haces. Úsala para responder, no abre nada. Ej.: "
        "«¿qué puedes hacer?», «explícame tu modo partida» (topic=modo partida)."
    )
    risk = Risk.GREEN
    game_policy = GamePolicy.ALLOWED
    category = Category.SYSTEM
    params_model = NyxInfoParams
    observe = True

    async def run(self, params: NyxInfoParams, ctx: ToolContext) -> ToolResult:
        text = find(params.topic)
        # Al modelo le llega todo el apartado; él lo resume en una o dos frases.
        return ToolResult(ok=True, message=" ".join(text.split()))
