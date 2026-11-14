"""¿Es buen momento para reiniciar y actualizar? (SPEC §15, paso 3).

Solo si Nyx no está haciendo nada que se pueda romper: sin una petición en curso, sin partida,
sin grabación ni operaciones de archivos, y sin una confirmación o un deshacer pendientes. Cada
parte de Nyx que pueda estar ocupada se registra con una función que dice por qué lo está.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

Busy = Callable[[], str | None]  # None si está libre; si no, por qué


@dataclass(slots=True)
class UpdateGate:
    checks: dict[str, Busy] = field(default_factory=dict)

    def add(self, name: str, busy: Busy) -> None:
        self.checks[name] = busy

    def blocked_by(self) -> list[str]:
        """Las razones por las que no es buen momento (vacío: se puede actualizar)."""
        out = []
        for name, busy in self.checks.items():
            try:
                why = busy()
            except Exception:  # si no se sabe, mejor esperar
                why = f"{name}: no se sabe"
            if why:
                out.append(why)
        return out

    def ready(self) -> bool:
        return not self.blocked_by()
