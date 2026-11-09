"""Interfaz común de los modelos de lenguaje (SPEC sección 2)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal, Protocol

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Role
    content: str


class LLMErrorKind(StrEnum):
    UNAVAILABLE = "unavailable"  # el servidor no responde
    MODEL_MISSING = "model_missing"  # el modelo no está descargado
    TIMEOUT = "timeout"  # se atascó (SPEC sección 14: 8 s)
    OTHER = "other"


class LLMError(Exception):
    def __init__(self, kind: LLMErrorKind, detail: str = "") -> None:
        super().__init__(f"{kind}: {detail}" if detail else str(kind))
        self.kind = kind


class LLMEngine(Protocol):
    async def warmup(self, prefix: Sequence[ChatMessage] = ()) -> None:
        """Carga el modelo en la GPU y procesa `prefix` para dejarlo en la caché de Ollama."""
        ...

    async def unload(self) -> None:
        """Libera la VRAM (al salir de Nyx)."""
        ...

    def stream(
        self, messages: Sequence[ChatMessage], *, schema: dict[str, Any] | None = None
    ) -> AsyncIterator[str]:
        """Texto de la respuesta a trozos según se genera."""
        ...
