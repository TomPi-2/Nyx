"""Contrato común de las herramientas (SPEC secciones 7, 8 y 9).

Cada herramienta declara:
- `name` y `description` (en español, con frases de ejemplo para el LLM),
- `params_model`: parámetros con tipos estrictos (pydantic),
- `risk`: verde, amarillo o rojo; lo aplica SafetyGuard, nunca el LLM,
- `game_policy`: permitida, diferida o bloqueada en partida (se aplica en la fase 5),
- `category`: para dar al LLM solo las herramientas del tema de la petición.
"""

from __future__ import annotations

from abc import ABC
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from nyx.safety.paths import PathPolicy
from nyx.safety.undo import Undo, UndoStack

if TYPE_CHECKING:
    from nyx.alarms.scheduler import AlarmScheduler
    from nyx.game.policy import GameGate
    from nyx.index.service import SystemIndex
    from nyx.organizer.store import OrganizerStore
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
    model_config = ConfigDict(arbitrary_types_allowed=True)

    ok: bool
    # Frase corta de lo ocurrido: va al registro y, si falla, es lo que se dice.
    message: str = ""
    # Burbuja opcional (resultado útil: «Captura guardada»). Sin ella, el éxito es silencioso.
    display: str | None = None
    secondary: str | None = None
    # `message` ya es la respuesta entera, en una frase para decir (6.20a): si la petición la
    # resolvió el router (una pregunta concreta: «¿cuánta batería me queda?»), se dice tal cual,
    # sin otra vuelta al LLM (la mitad del trabajo de la gráfica). Si la pidió el LLM (una
    # pregunta más libre), el resultado vuelve a él como siempre.
    speak: bool = False
    # False: este resultado no vuelve al LLM aunque la herramienta sea de consulta (`observe`):
    # no hay nada que contar («Copiado», «Cronómetro en marcha») y se ahorra una vuelta.
    observe: bool = True
    # Contenido de fuera (portapapeles, webs, archivos): es dato, nunca órdenes. Solo lo ve el
    # LLM, marcado como información (brain/agent.py); no va al registro de acciones ni a la
    # memoria corta, que guardan `message`.
    external: str | None = None
    data: dict[str, Any] = {}
    # Acciones amarillas: cómo revertirla (se ofrece «Deshacer» 30 s).
    undo: Undo | None = Field(default=None, exclude=True)

    @classmethod
    def fail(cls, message: str, suggestion: str | None = None) -> ToolResult:
        return cls(ok=False, message=message, display=message, secondary=suggestion)


@dataclass
class ToolContext:
    index: SystemIndex
    settings: Settings
    undo: UndoStack = field(default_factory=UndoStack)
    paths: PathPolicy = field(default_factory=PathPolicy)
    alarms: AlarmScheduler | None = None
    # Listas y tareas (8.01); la pone services.py.
    organizer: OrganizerStore | None = None
    # Abre la ventana de Ajustes de Nyx (sección o None); la pone services.py.
    open_nyx_settings: Callable[[str | None], Awaitable[None]] | None = None
    # Cierra la ventana de Ajustes («cierra tus ajustes»); la pone services.py.
    close_nyx_settings: Callable[[], Awaitable[None]] | None = None
    # «Reiníciate»: pide a la app que reinicie el núcleo; la pone services.py.
    restart_nyx: Callable[[], Awaitable[None]] | None = None
    # La cola de la partida (lo diferido); la pone services.py.
    game: GameGate | None = None
    # Cambia ajustes de Nyx por el mismo camino que la ventana de Ajustes (nyx_control, 6.04).
    # Devuelve lo que se aplica al reiniciar; la pone services.py.
    apply_settings: Callable[[dict[str, Any]], Awaitable[list[str]]] | None = None
    # Saca junto a Nyx el panel de su color, su tamaño o los paneles (nyx_panel, 9.11): «color»,
    # «size» o «tint»; la pone services.py.
    open_nyx_panel: Callable[[str], Awaitable[None]] | None = None
    # «Nyx, actualízate» (nyx_update, 9.06): aplica la versión descargada o dice que no hay;
    # devuelve lo que se dice. La pone services.py.
    update_now: Callable[[], Awaitable[str]] | None = None
    # Dictado (8.04): lo comparte con el pipeline, que escribe lo que oye; lo pone services.py.
    dictation: Any = None
    # Modos (8.10): el gestor (nyx/modes/manager.py); lo pone services.py.
    modes: Any = None


@dataclass
class Prepared:
    """Lo que va a hacer una llamada, resuelto antes de ejecutarla (SafetyGuard lo revisa y,
    si es roja, es lo que se confirma: se ejecuta exactamente esto, no se vuelve a resolver)."""

    summary: str  # «Mover 5 archivos de Descargas a Documentos»
    detail: str = ""  # línea secundaria de la confirmación (nombres de archivos…)
    paths: list[Path] = field(default_factory=list)  # lo que se mueve, renombra o borra
    targets: list[Path] = field(default_factory=list)  # dónde se escribe (destinos)
    count: int = 0  # elementos afectados
    risk: Risk | None = None  # más riesgo que el de la herramienta (cambios sin guardar)
    # La herramienta ha comprobado que esto solo lee (lista cerrada, `run_powershell`): baja a
    # verde, pero solo si la herramienta lo permite (`Tool.green_when_read_only`).
    read_only: bool = False
    payload: Any = None
    error: ToolResult | None = None  # no se puede hacer (no encuentro la carpeta…)


class Tool[P: Params](ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    risk: ClassVar[Risk]
    game_policy: ClassVar[GamePolicy]
    category: ClassVar[Category]
    params_model: type[P]
    timeout_s: ClassVar[float] = 10.0
    # Consulta algo que hay que contar (listar, buscar, ver alarmas…): su resultado vuelve al
    # LLM para que lo diga en una frase (bucle de agente, brain/agent.py).
    observe: ClassVar[bool] = False
    # False: existe para los planes pero el modelo no la ve (ahorra contexto, tarea 6.18).
    llm_visible: ClassVar[bool] = True
    # True: lo preparado con `read_only` se ejecuta en verde aunque la herramienta sea roja.
    # Solo `run_powershell` (excepción de solo lectura, decidida por el usuario el 2026-11-13).
    green_when_read_only: ClassVar[bool] = False

    # Cada herramienta redefine `run` (sencillas) o `prepare` + `execute` (las que tocan
    # archivos o ventanas: SafetyGuard revisa lo preparado antes de ejecutarlo).

    async def run(self, params: P, ctx: ToolContext) -> ToolResult:
        prepared = await self.prepare(params, ctx)
        return prepared.error or await self.execute(params, ctx, prepared)

    async def prepare(self, params: P, ctx: ToolContext) -> Prepared:
        """Resuelve qué se va a tocar. Las herramientas verdes sencillas no lo necesitan."""
        return Prepared(summary=self.name)

    async def execute(self, params: P, ctx: ToolContext, prepared: Prepared) -> ToolResult:
        """Ejecuta lo preparado. Por defecto, `run` (herramientas sin preparación)."""
        return await self.run(params, ctx)

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
