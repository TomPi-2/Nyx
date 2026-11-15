# SPDX-License-Identifier: GPL-3.0-only OR MIT
# También con licencia MIT, como el manifiesto: lo usa el kit de extensiones (7.12-7.13).
"""Las herramientas de una extensión con código (`tools/tools.json`; tarea 7.07).

Nyx tiene que conocerlas sin arrancar la extensión (se arranca la primera vez que se usa), así
que van descritas en el paquete:

```json
[
  {
    "name": "obs_start_recording",
    "description": "Empieza a grabar en OBS.",
    "parameters": {"properties": {}, "required": []},
    "risk": "green",
    "uses": ["net:localhost:4455"],
    "game_policy": "allowed"
  }
]
```

- `parameters`: un objeto JSON Schema sencillo: propiedades de tipo `string`, `integer`,
  `number` o `boolean`, con `description` y, si se quiere, `enum`.
- `risk`: el que declara la extensión. Nyx usa **el mayor** entre ese y el mínimo de los
  permisos que dice usar (`uses`, que tienen que estar en el manifiesto). Sin `uses`, el de
  todos sus permisos: ante la duda, el más alto.
- `game_policy`: en partida (por defecto, «al terminar»). El del manifiesto, si lo pone,
  manda.
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator

from nyx.ext.manifest import _NAME, Manifest, ManifestError, parse_permission
from nyx.tools.base import GamePolicy, Risk

TOOLS_FILE = "tools/tools.json"
MAX_TOOLS_BYTES = 64 * 1024
MAX_TOOLS = 20

_RISK_ORDER = (Risk.GREEN, Risk.YELLOW, Risk.RED)


class Prop(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    type: Literal["string", "integer", "number", "boolean"]
    description: str = Field(default="", max_length=200)
    enum: tuple[str, ...] | None = Field(default=None, max_length=40)


class Params(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    properties: dict[str, Prop] = Field(default_factory=dict, max_length=12)
    required: tuple[str, ...] = ()

    @field_validator("properties")
    @classmethod
    def _names(cls, props: dict[str, Prop]) -> dict[str, Prop]:
        bad = [p for p in props if not _NAME.match(p)]
        if bad:
            raise ValueError(f"nombres de parámetro no válidos: {', '.join(bad)}")
        return props


class ToolSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    name: str = Field(pattern=_NAME.pattern)
    description: str = Field(min_length=3, max_length=300)
    parameters: Params = Field(default_factory=Params)
    risk: Literal["green", "yellow", "red"] = "green"
    uses: tuple[str, ...] = ()
    game_policy: Literal["allowed", "deferred", "blocked"] = "deferred"


_LIST: TypeAdapter[list[ToolSpec]] = TypeAdapter(list[ToolSpec])


def load_tools(raw: bytes, manifest: Manifest) -> tuple[ToolSpec, ...]:
    """Las herramientas validadas, o `ManifestError` con lo que falla, en español."""
    if len(raw) > MAX_TOOLS_BYTES:
        raise ManifestError("tools.json es demasiado grande")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ManifestError(f"tools.json no es JSON válido: {e}") from e
    if not isinstance(data, list) or not 1 <= len(data) <= MAX_TOOLS:
        raise ManifestError(f"tools.json tiene que ser una lista de 1 a {MAX_TOOLS} herramientas")
    try:
        # Desde el JSON tal cual: en modo estricto, las listas valen como tuplas.
        tools = tuple(_LIST.validate_json(raw))
    except ValidationError as e:
        first = e.errors()[0]
        where = ".".join(str(x) for x in first["loc"])
        raise ManifestError(f"tools.json: {where}: {first['msg']}") from e
    names = [t.name for t in tools]
    if len(set(names)) != len(names):
        raise ManifestError("tools.json: herramientas con el mismo nombre")
    granted = set(manifest.permissions)
    for t in tools:
        missing = [p for p in t.uses if str(parse_permission(p)) not in granted]
        if missing:
            raise ManifestError(
                f"«{t.name}» usa permisos que el manifiesto no pide: {', '.join(missing)}"
            )
        unknown = [p for p in t.parameters.required if p not in t.parameters.properties]
        if unknown:
            raise ManifestError(f"«{t.name}»: obligatorios sin definir: {', '.join(unknown)}")
    return tools


def effective_risk(spec: ToolSpec, manifest: Manifest) -> Risk:
    """El mayor entre el riesgo declarado y el mínimo de los permisos que usa (o de todos)."""
    uses = spec.uses or manifest.permissions
    floor = [parse_permission(p).min_risk for p in uses]
    declared = Risk(spec.risk)
    return max([declared, *floor], key=_RISK_ORDER.index)


def game_policy(spec: ToolSpec, manifest: Manifest) -> GamePolicy:
    return manifest.game_policy.get(spec.name, GamePolicy(spec.game_policy))
