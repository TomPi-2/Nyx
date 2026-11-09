"""Executor: valida, revisa y ejecuta llamadas a herramientas, una tras otra (SPEC sección 3).

Por cada llamada:
1. Valida los parámetros con el esquema de la herramienta.
2. `prepare`: resuelve exactamente qué se va a tocar (archivos, ventanas…).
3. SafetyGuard decide: ejecutar, ejecutar con deshacer, pedir confirmación o bloquear.
4. Si es roja, pide confirmación (clic o voz) y ejecuta exactamente lo preparado.
5. Ejecuta con tiempo máximo; un fallo nunca tumba el núcleo.
6. Si es amarilla y salió bien, guarda cómo deshacerla (30 s).
7. Todo queda en el registro de acciones.

En un plan de varios pasos, el primer fallo (o una cancelación) detiene los siguientes.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from nyx.safety.action_log import ActionLog, Decision
from nyx.safety.guard import SafetyGuard, Verdict
from nyx.tools.base import Prepared, Tool, ToolContext, ToolResult
from nyx.tools.registry import ToolRegistry

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Confirmation:
    summary: str  # «Mandar a la papelera 3 archivos»
    detail: str  # «de Descargas: a.pdf, b.pdf, c.pdf»
    click_only: bool  # más de 50 elementos o fuera de las carpetas del usuario


ConfirmFn = Callable[[Confirmation], Awaitable[bool]]


def cancelled_result(summary: str) -> ToolResult:
    return ToolResult(
        ok=False,
        message="Cancelado",
        display="Cancelado",
        secondary=summary,
        data={"cancelled": True},
    )


class Executor:
    def __init__(
        self,
        registry: ToolRegistry,
        ctx: ToolContext,
        *,
        guard: SafetyGuard | None = None,
        action_log: ActionLog | None = None,
        confirm: ConfirmFn | None = None,
    ) -> None:
        self.registry = registry
        self.ctx = ctx
        self.guard = guard or SafetyGuard(ctx.paths)
        self.log = action_log
        self.confirm = confirm

    def _record(
        self,
        tool: Tool[Any] | None,
        name: str,
        params: dict[str, Any],
        decision: Decision,
        result: ToolResult | None,
        phrase: str,
    ) -> None:
        if self.log is None:
            return
        self.log.write(
            tool=name,
            params=params,
            decision=decision,
            ok=None if result is None else result.ok,
            message="" if result is None else result.message,
            phrase=phrase,
            risk=str(tool.risk) if tool is not None else "",
        )

    async def run(self, call: ToolCall, *, phrase: str = "") -> ToolResult:
        tool = self.registry.get(call.name)
        if tool is None:
            log.warning("Herramienta desconocida: %s", call.name)
            result = ToolResult.fail("No sé hacer eso todavía")
            self._record(None, call.name, call.arguments, Decision.INVALID, result, phrase)
            return result
        try:
            params = tool.params_model.model_validate(call.arguments)
        except ValidationError as e:
            log.warning("Parámetros no válidos para %s: %s", call.name, e)
            result = ToolResult.fail("No he entendido bien qué hacer", "¿lo repites?")
            self._record(tool, call.name, call.arguments, Decision.INVALID, result, phrase)
            return result
        args = params.model_dump(exclude_none=True)
        t0 = time.perf_counter()
        try:
            prepared = await asyncio.wait_for(tool.prepare(params, self.ctx), tool.timeout_s)
        except TimeoutError:
            prepared = Prepared("", error=ToolResult.fail("Ha tardado demasiado"))
        except Exception:
            log.exception("Fallo preparando %s", call.name)
            prepared = Prepared("", error=ToolResult.fail("Algo ha fallado al prepararlo"))
        if prepared.error is not None:
            self._record(tool, call.name, args, Decision.EXECUTED, prepared.error, phrase)
            return prepared.error

        decision = self.guard.evaluate(tool.risk, prepared)
        logged = Decision.EXECUTED
        if decision.verdict is Verdict.BLOCK:
            log.warning("SafetyGuard bloquea %s: %s", call.name, decision.reason)
            result = ToolResult.fail(decision.reason, "por seguridad")
            self._record(tool, call.name, args, Decision.BLOCKED, result, phrase)
            return result
        if decision.verdict is Verdict.CONFIRM:
            if self.confirm is None:
                result = ToolResult.fail("Necesito que lo confirmes y ahora no puedo preguntarte")
                self._record(tool, call.name, args, Decision.BLOCKED, result, phrase)
                return result
            ok = await self.confirm(
                Confirmation(prepared.summary, prepared.detail, decision.click_only)
            )
            if not ok:
                result = cancelled_result(prepared.summary)
                self._record(tool, call.name, args, Decision.CANCELLED, result, phrase)
                return result
            logged = Decision.CONFIRMED

        try:
            result = await asyncio.wait_for(
                tool.execute(params, self.ctx, prepared), tool.timeout_s
            )
        except TimeoutError:
            result = ToolResult.fail("Ha tardado demasiado")
        except Exception:
            log.exception("Fallo en la herramienta %s", call.name)
            result = ToolResult.fail("Algo ha fallado al hacerlo")
        if result.ok and result.undo is not None:
            entry = self.ctx.undo.push(result.undo)
            result.data["undo_id"] = entry.id
        log.info(
            "Acción %s(%s) → %s en %d ms: %s",
            call.name,
            args,
            "ok" if result.ok else "fallo",
            round((time.perf_counter() - t0) * 1000),
            result.message,
        )
        self._record(tool, call.name, args, logged, result, phrase)
        return result

    async def run_plan(self, calls: list[ToolCall], *, phrase: str = "") -> list[ToolResult]:
        results: list[ToolResult] = []
        for call in calls:
            result = await self.run(call, phrase=phrase)
            results.append(result)
            if not result.ok:
                break
        return results
