"""Selector de herramientas por petición (0.6, tarea 6.20b).

Objetivo: poder instalar muchas extensiones sin perder rendimiento ni subir el tiempo medio de
respuesta. Medido en el PC de referencia (`docs/benchmarks/grupos-6.20b.md`):

- Con la lista de herramientas en la caché de Ollama, el primer token sale en ~0,07 s. Cada
  cambio en la lista obliga a evaluar de nuevo desde el primer punto que cambia.
- Cambiar de grupo en cada petición (fijas + el grupo del tema) **no** mejora el acierto del 7B
  y sube el tiempo medio unos 160 ms con las 39 herramientas de la 0.6.

Por eso la lista solo se recorta cuando no cabe:

1. **Si todas caben** en el presupuesto (`tools_budget`, una parte del contexto), el modelo las
   ve todas y siempre en el mismo orden: ni un solo cambio de caché.
2. **Si no caben** (muchas extensiones, o un contexto más pequeño), los grupos funcionan como
   una caché: la lista son las fijas y los grupos usados hace poco. Un grupo nuevo se añade
   **al final** (lo de antes sigue en la caché: solo se evalúa lo nuevo) y, si no cabe, sale
   el que lleve más tiempo sin usarse. Una frase sin pistas no cambia nada.

En el bucle de agente (otra vuelta de la misma petición) la lista no cambia.

3. **Índice de último recurso** (0.7, tarea 7.15; antes 6.20c): si no caben y la frase no trae
   ninguna pista, el cerebro pregunta al modelo en una llamada corta qué grupos hacen falta, con
   una línea por grupo (`index_lines`), y se los pasa a `select(picked=…)`. Solo entonces: con
   todo en la lista (lo de siempre hoy) no se pregunta nada.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from typing import Any

from nyx.index.aliases import normalize
from nyx.tools.groups import FIXED, GROUPS, Group
from nyx.tools.registry import ToolRegistry

log = logging.getLogger(__name__)

MAX_GROUPS = 3  # grupos que una sola frase puede pedir a la vez
TOOLS_SHARE = 0.4  # parte del contexto (`llm.num_ctx`) que pueden ocupar las herramientas
CHARS_PER_TOKEN = 5.5  # esquemas JSON con qwen2.5 (medido en la 6.18)


def tools_budget(num_ctx: int) -> int:
    """Caracteres de esquema que caben en el prompt con ese contexto. Con 12.288 (0.6) caben
    las 39 herramientas; con 8.192 (6.20d) entran en juego los grupos."""
    return int(num_ctx * TOOLS_SHARE * CHARS_PER_TOKEN)


def _chars(schema: dict[str, Any]) -> int:
    return len(json.dumps(schema, ensure_ascii=False))


class ToolSelector:
    def __init__(
        self,
        registry: ToolRegistry,
        groups: Sequence[Group] = GROUPS,
        fixed: Sequence[str] = FIXED,
        *,
        budget_chars: int = tools_budget(12288),
        max_groups: int = MAX_GROUPS,
    ) -> None:
        self._schemas = {t.name: t.schema() for t in registry.all() if t.llm_visible}
        self.fixed = tuple(n for n in fixed if n in self._schemas)
        self.groups = tuple(groups)
        self._by_name = {g.name: g for g in self.groups}
        self._patterns = {
            g.name: re.compile(r"\b(?:" + "|".join(g.keywords) + ")") for g in self.groups
        }
        self.max_groups = max_groups
        self.budget_chars = budget_chars
        self._sizes = {
            g.name: sum(_chars(self._schemas[n]) for n in g.tools if n in self._schemas)
            for g in self.groups
        }
        self._fixed_chars = sum(_chars(self._schemas[n]) for n in self.fixed)
        # Todas caben: se ven todas, en el orden del registro (el de siempre, el medido).
        self.all_fit = sum(_chars(s) for s in self._schemas.values()) <= budget_chars
        self._everything = list(self._schemas.values())
        # Todas las herramientas (también las que no se ven): una llamada escrita como texto a
        # una que no estaba en la lista se reconoce y se ejecuta igual (existe).
        self.names = frozenset(t.name for t in registry.all())
        self.current: tuple[str, ...] = ()  # grupos de la lista vigente, en su orden
        self._used: dict[str, int] = {}  # grupo → cuándo se pidió por última vez
        self._clock = 0

    def groups_for(self, text: str) -> tuple[str, ...]:
        """Los grupos cuyo tema aparece en `text`, en el orden de `GROUPS` (como mucho
        `max_groups`: los de más coincidencias)."""
        norm = normalize(text)
        if not norm:
            return ()
        hits = {g.name: n for g in self.groups if (n := len(self._patterns[g.name].findall(norm)))}
        if len(hits) > self.max_groups:
            order = [g.name for g in self.groups]
            best = sorted(hits, key=lambda name: (-hits[name], order.index(name)))
            hits = {name: hits[name] for name in best[: self.max_groups]}
        return tuple(g.name for g in self.groups if g.name in hits)

    def tools_for(self, groups: Sequence[str]) -> list[dict[str, Any]]:
        """Fijas y después los grupos en el orden dado (el de la caché)."""
        names = list(self.fixed)
        for name in groups:
            group = self._by_name.get(name)
            if group is not None:
                names += [n for n in group.tools if n in self._schemas and n not in names]
        return [self._schemas[n] for n in names]

    def _size(self, groups: Sequence[str]) -> int:
        return self._fixed_chars + sum(self._sizes.get(g, 0) for g in groups)

    def needs_index(self, text: str) -> bool:
        """¿Hay que preguntar al modelo por los grupos? (no caben y la frase no da pistas)"""
        # «Hola» o «gracias» no necesitan herramientas: no se gasta una llamada en ellas.
        return not self.all_fit and not self.groups_for(text) and len(normalize(text).split()) > 2

    def index_lines(self) -> list[str]:
        """Una línea por grupo («nombre: de qué va») para que el modelo elija."""
        return [f"{g.name}: {g.about}" for g in self.groups]

    def select(
        self, text: str, *, keep: bool = False, picked: Sequence[str] = ()
    ) -> list[dict[str, Any]]:
        """Herramientas para esta petición. `keep`: otra vuelta de la misma petición.
        `picked`: grupos elegidos con el índice de último recurso (7.15)."""
        if self.all_fit:
            return self._everything
        if keep:
            return self.tools_for(self.current)
        wanted = (
            self.groups_for(text)
            or tuple(g for g in picked if g in self._by_name)[: self.max_groups]
        )
        self._clock += 1
        for name in wanted:
            self._used[name] = self._clock
        missing = [g for g in wanted if g not in self.current]
        if not missing:
            return self.tools_for(self.current)
        groups = [*self.current, *missing]
        # Si no cabe, sale el grupo usado hace más tiempo (nunca uno que pide esta frase).
        while self._size(groups) > self.budget_chars:
            spare = [g for g in groups if g not in wanted]
            if not spare:
                break
            groups.remove(min(spare, key=lambda g: self._used.get(g, 0)))
        self.current = tuple(groups)
        log.info("Herramientas: fijas + %s", ", ".join(self.current))
        return self.tools_for(self.current)
