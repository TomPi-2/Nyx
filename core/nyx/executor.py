"""Executor: valida y ejecuta llamadas a herramientas, una tras otra (SPEC sección 3, paso 9).

- Los parámetros se validan con el esquema de la herramienta antes de tocar nada.
- Cada herramienta tiene un tiempo máximo; un fallo nunca tumba el núcleo.
- En un plan de varios pasos, el primer fallo detiene los siguientes.
- SafetyGuard (confirmar, deshacer) y el registro de acciones llegan en el bloque 3b.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from nyx.tools.base import Risk, ToolContext, ToolResult
from nyx.tools.registry import ToolRegistry

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


class Executor:
    def __init__(self, registry: ToolRegistry, ctx: ToolContext) -> None:
        self.registry = registry
        self.ctx = ctx

    async def run(self, call: ToolCall) -> ToolResult:
        tool = self.registry.get(call.name)
        if tool is None:
            log.warning("Herramienta desconocida: %s", call.name)
            return ToolResult.fail("No sé hacer eso todavía")
        try:
            params = tool.params_model.model_validate(call.arguments)
        except ValidationError as e:
            log.warning("Parámetros no válidos para %s: %s", call.name, e)
            return ToolResult.fail("No he entendido bien qué hacer", "¿lo repites?")
        if tool.risk is not Risk.GREEN:
            # Hasta que llegue SafetyGuard (3b), nada que no sea verde se ejecuta.
            log.warning("%s es de riesgo %s y aún no hay confirmaciones", call.name, tool.risk)
            return ToolResult.fail("Aún no puedo hacer eso", "llegará pronto")
        t0 = time.perf_counter()
        try:
            result = await asyncio.wait_for(tool.run(params, self.ctx), tool.timeout_s)
        except TimeoutError:
            result = ToolResult.fail("Ha tardado demasiado")
        except Exception:
            log.exception("Fallo en la herramienta %s", call.name)
            result = ToolResult.fail("Algo ha fallado al hacerlo")
        log.info(
            "Acción %s(%s) → %s en %d ms: %s",
            call.name,
            params.model_dump(exclude_none=True),
            "ok" if result.ok else "fallo",
            round((time.perf_counter() - t0) * 1000),
            result.message,
        )
        return result

    async def run_plan(self, calls: list[ToolCall]) -> list[ToolResult]:
        results: list[ToolResult] = []
        for call in calls:
            result = await self.run(call)
            results.append(result)
            if not result.ok:
                break
        return results
