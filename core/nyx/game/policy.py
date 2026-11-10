"""Qué se puede hacer en partida (SPEC sección 9) y la cola de lo diferido.

Cada herramienta trae su política (permitida, diferida o bloqueada); el usuario puede moverla
de columna en los ajustes (`game.policies`). Las acciones rojas se difieren salvo en el modo
«normal»: su confirmación no se vería en el monitor del juego.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
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


@dataclass
class GameGate:
    settings: GameSettings
    active: bool = False
    queue: list[Deferred] = field(default_factory=list)

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

    def defer(self, call: ToolCall, phrase: str, summary: str) -> None:
        log.info("En partida, se deja para después: %s(%s)", call.name, call.arguments)
        self.queue.append(Deferred(call, phrase, summary))

    def take(self) -> list[Deferred]:
        pending, self.queue = self.queue, []
        return pending
