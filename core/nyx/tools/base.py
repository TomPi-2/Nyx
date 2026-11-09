"""Contrato común de las herramientas (SPEC secciones 7, 8 y 9).

Cada herramienta declara:
- `name` y `description` (en español, con frases de ejemplo para el LLM),
- `params_model`: parámetros con tipos estrictos (pydantic),
- `risk`: verde, amarillo o rojo; lo aplica SafetyGuard, nunca el LLM,
- `game_policy`: permitida, diferida o bloqueada en partida (se aplica en la fase 5),
- `category`: para dar al LLM solo las herramientas del tema de la petición.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from nyx.index.service import SystemIndex
    from nyx.settings.model import Settings


class Risk(StrEnum):
    GREEN = "green"  # se ejecuta sin preguntar
    YELLOW = "yellow"  # se ejecuta y ofrece deshacer 30 s
    RED = "red"  # pide confirmación antes


class GamePolicy(StrEnum):
    ALLOWED = "allowed"
    DEFERRED = "deferred"  # «te lo hago al terminar la partida»
    BLOCKED = "blocked"


class Category(StrEnum):
    APPS = "apps"
    WINDOWS = "windows"
    WEB = "web"
    SYSTEM = "system"
    FILES = "files"
    AUDIO = "audio"
    CAPTURE = "capture"
    TIME = "time"


class Params(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ToolResult(BaseModel):
    ok: bool
    # Frase corta de lo ocurrido: va al registro y, si falla, es lo que se dice.
    message: str = ""
    # Burbuja opcional (resultado útil: «Captura guardada»). Sin ella, el éxito es silencioso.
    display: str | None = None
    secondary: str | None = None
    speak: bool = False  # decir `message` en voz alta aunque haya ido bien
    data: dict[str, Any] = {}

    @classmethod
    def fail(cls, message: str, suggestion: str | None = None) -> ToolResult:
        return cls(ok=False, message=message, display=message, secondary=suggestion)


@dataclass
class ToolContext:
    index: SystemIndex
    settings: Settings


class Tool[P: Params](ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    risk: ClassVar[Risk]
    game_policy: ClassVar[GamePolicy]
    category: ClassVar[Category]
    params_model: type[P]
    timeout_s: ClassVar[float] = 10.0

    @abstractmethod
    async def run(self, params: P, ctx: ToolContext) -> ToolResult: ...

    def schema(self) -> dict[str, Any]:
        """Definición en el formato de herramientas de Ollama (fase 3c)."""
        parameters = self.params_model.model_json_schema()
        parameters.pop("title", None)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": parameters,
            },
        }
