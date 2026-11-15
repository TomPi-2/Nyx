"""Las herramientas de una extensión con código, como `Tool` normales de Nyx (tarea 7.07).

Cada una sale de `tools/tools.json` (tools_spec.py): su nombre, descripción, parámetros, riesgo
(nunca menor que el de los permisos que usa) y política en partida. Para Nyx son herramientas
como las suyas: pasan por `SafetyGuard` (confirmación si son rojas, deshacer si amarillas), por
el modo partida y por el registro de acciones. Al usarlas, el host (host.py) arranca la
extensión encerrada si hace falta y le pasa la llamada.

La extensión contesta con texto o con un objeto `{"message", "display", "secondary",
"speak"}`; cualquier otra cosa se toma como texto. Si falla, se cae o tarda demasiado, la
herramienta falla con un mensaje claro y Nyx sigue igual.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import Field, create_model

from nyx.ext.host import ExtensionCrashError, ExtensionHost
from nyx.ext.manifest import ManifestError
from nyx.ext.rpc import RpcError
from nyx.ext.store import Installed
from nyx.ext.tools_spec import (
    TOOLS_FILE,
    ToolSpec,
    effective_risk,
    game_policy,
    load_tools,
)
from nyx.tools.base import Category, Params, Tool, ToolContext, ToolResult

log = logging.getLogger(__name__)

#: Lo que se espera a una herramienta de extensión (red, OBS…) antes de darla por colgada.
TIMEOUT_S = 20.0
MAX_TEXT = 500

_TYPES: dict[str, type] = {"string": str, "integer": int, "number": float, "boolean": bool}


class ExtTool(Tool[Params]):
    """Base de las herramientas de extensión; `make_tools` crea una subclase por herramienta."""

    category = Category.APPS
    timeout_s = TIMEOUT_S + 5
    ext_id: str = ""
    package: Any = None
    host: ExtensionHost | None = None

    async def run(self, params: Params, ctx: ToolContext) -> ToolResult:
        assert self.host is not None
        args = params.model_dump(exclude_none=True)
        try:
            answer = await self.host.call(self.ext_id, self.package, self.name, args, TIMEOUT_S)
        except RpcError as e:
            log.info("Extensión %s, %s: %s", self.ext_id, self.name, e)
            return ToolResult.fail("La extensión no ha podido hacerlo", str(e)[:MAX_TEXT])
        except ExtensionCrashError as e:
            return ToolResult.fail("La extensión no responde", str(e)[:MAX_TEXT])
        return _result(answer)


def _result(answer: Any) -> ToolResult:
    if isinstance(answer, dict):
        message = str(answer.get("message") or "Hecho")[:MAX_TEXT]
        display = answer.get("display")
        secondary = answer.get("secondary")
        return ToolResult(
            ok=True,
            message=message,
            display=str(display)[:MAX_TEXT] if display else None,
            secondary=str(secondary)[:MAX_TEXT] if secondary else None,
            speak=bool(answer.get("speak", False)),
            observe=True,
        )
    text = "Hecho" if answer is None else str(answer)[:MAX_TEXT]
    return ToolResult(ok=True, message=text, observe=True)


def _params_model(spec: ToolSpec) -> type[Params]:
    fields: dict[str, Any] = {}
    for name, prop in spec.parameters.properties.items():
        kind: Any = Literal[prop.enum] if prop.enum else _TYPES[prop.type]
        required = name in spec.parameters.required
        if required:
            fields[name] = (kind, Field(description=prop.description))
        else:
            fields[name] = (kind | None, Field(default=None, description=prop.description))
    model: type[Params] = create_model(f"P_{spec.name}", __base__=Params, **fields)
    return model


def make_tools(ext: Installed, host: ExtensionHost) -> list[Tool[Any]]:
    """Las herramientas de `ext` para registrarlas en Nyx (ExtensionManager.tool_factory)."""
    path = ext.path / TOOLS_FILE
    try:
        specs = load_tools(path.read_bytes(), ext.manifest)
    except OSError as e:
        raise ManifestError(f"falta {TOOLS_FILE}") from e
    tools: list[Tool[Any]] = []
    for spec in specs:
        cls = type(
            f"Ext_{spec.name}",
            (ExtTool,),
            {
                "name": spec.name,
                "description": spec.description,
                "risk": effective_risk(spec, ext.manifest),
                "game_policy": game_policy(spec, ext.manifest),
                "params_model": _params_model(spec),
                "observe": True,
                "ext_id": ext.id,
                "package": ext.path,
                "host": host,
            },
        )
        tools.append(cls())
    return tools
