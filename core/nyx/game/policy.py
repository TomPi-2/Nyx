"""Qué se puede hacer en partida (SPEC sección 9) y la cola de lo diferido.

Cada herramienta trae su política (permitida, diferida o bloqueada); el usuario puede moverla
de columna en los ajustes (`game.policies`). Las acciones rojas se difieren salvo en el modo
«normal»: su confirmación no se vería en el monitor del juego.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from nyx.tools.base import GamePolicy, Risk

if TYPE_CHECKING:
    from nyx.executor import ToolCall
    from nyx.settings.model import GameSettings
    from nyx.tools.base import Tool

log = logging.getLogger(__name__)


@dataclass
class Deferred:
    call: ToolCall
    phrase: str
    summary: str
    voice: bool = False  # se pidió hablando: el resumen del final también se dice


def _load(path: Path) -> list[Deferred]:
    """La cola guardada (sobrevive a un reinicio o a un corte de luz, SPEC sección 14)."""
    from nyx.executor import ToolCall

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [
            Deferred(
                ToolCall(d["name"], dict(d["arguments"])), d["phrase"], d["summary"], d["voice"]
            )
            for d in raw
        ]
    except FileNotFoundError:
        return []
    except (OSError, ValueError, KeyError, TypeError):
        log.warning("Cola de partida dañada en %s: se descarta", path, exc_info=True)
        return []


@dataclass
class GameGate:
    settings: GameSettings
    active: bool = False
    queue: list[Deferred] = field(default_factory=list)
    path: Path | None = None  # dónde se guarda la cola (None: solo en memoria)

    @property
    def mode(self) -> str:
        return self.settings.mode

    def policy_for(self, tool: Tool[object]) -> GamePolicy:  # type: ignore[type-var]
        if not self.active:
            return GamePolicy.ALLOWED
        override = self.settings.policies.get(tool.name)
        policy = GamePolicy(override) if override else tool.game_policy
        if policy is GamePolicy.ALLOWED and tool.risk is Risk.RED and self.mode != "normal":
            return GamePolicy.DEFERRED
        return policy

    def defer(self, call: ToolCall, phrase: str, summary: str, *, voice: bool = False) -> None:
        log.info("En partida, se deja para después: %s(%s)", call.name, call.arguments)
        self.queue.append(Deferred(call, phrase, summary, voice))
        self._save()

    def take(self) -> list[Deferred]:
        pending, self.queue = self.queue, []
        self._save()
        return pending

    def cancel(self, which: int | None = None) -> list[Deferred]:
        """Quita una acción pendiente (por su posición, desde 0) o todas (None)."""
        if which is None:
            gone, self.queue = self.queue, []
        elif 0 <= which < len(self.queue):
            gone = [self.queue.pop(which)]
        else:
            gone = []
        if gone:
            self._save()
        return gone

    def load(self) -> None:
        if self.path is not None:
            self.queue = _load(self.path)

    def _save(self) -> None:
        if self.path is None:
            return
        data = [
            {
                "name": d.call.name,
                "arguments": d.call.arguments,
                "phrase": d.phrase,
                "summary": d.summary,
                "voice": d.voice,
            }
            for d in self.queue
        ]
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            log.warning("No se pudo guardar la cola de partida", exc_info=True)
