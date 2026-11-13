"""SafetyGuard (SPEC sección 8): decide con reglas fijas, nunca el LLM, qué pasa con cada acción.

- Verde: se ejecuta.
- Amarillo: se ejecuta y se ofrece deshacer 30 s.
- Rojo: se pide confirmación. Solo con clic si afecta a más de 50 elementos o a algo fuera
  de las carpetas del usuario.
- Bloqueado: toca rutas protegidas (sistema, raíces de disco, Nyx, carpetas principales).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from nyx.safety.paths import PathPolicy
from nyx.tools.base import Prepared, Risk

CLICK_ONLY_COUNT = 50


class Verdict(StrEnum):
    RUN = "run"
    RUN_WITH_UNDO = "run_with_undo"
    CONFIRM = "confirm"
    BLOCK = "block"


@dataclass(frozen=True, slots=True)
class Decision:
    verdict: Verdict
    risk: Risk
    click_only: bool = False
    reason: str = ""


def _max_risk(a: Risk, b: Risk | None) -> Risk:
    order = [Risk.GREEN, Risk.YELLOW, Risk.RED]
    return a if b is None or order.index(a) >= order.index(b) else b


class SafetyGuard:
    def __init__(self, paths: PathPolicy) -> None:
        self.paths = paths

    def evaluate(
        self, tool_risk: Risk, prepared: Prepared, *, green_when_read_only: bool = False
    ) -> Decision:
        # El riesgo de la herramienta es el mínimo, salvo una excepción: lo que la herramienta
        # ha comprobado que solo lee, si la herramienta lo permite (`run_powershell`). Las
        # rutas protegidas se miran igual.
        if green_when_read_only and prepared.read_only and prepared.risk is None:
            risk = Risk.GREEN
        else:
            risk = _max_risk(tool_risk, prepared.risk)
        protected = [p for p in prepared.paths if self.paths.protected(p)]
        protected += [t for t in prepared.targets if self.paths.protected_target(t)]
        if protected:
            return Decision(
                Verdict.BLOCK, risk, reason=f"No toco {protected[0]}: es una ruta protegida"
            )
        if risk is Risk.GREEN:
            return Decision(Verdict.RUN, risk)
        if risk is Risk.YELLOW:
            return Decision(Verdict.RUN_WITH_UNDO, risk)
        touched = [*prepared.paths, *prepared.targets]
        outside = any(not self.paths.inside_user(p) for p in touched)
        click_only = prepared.count > CLICK_ONLY_COUNT or outside
        return Decision(Verdict.CONFIRM, risk, click_only=click_only)
