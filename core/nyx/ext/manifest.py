# SPDX-License-Identifier: GPL-3.0-only OR MIT
# También con licencia MIT (decisión del 2026-11-14), para el kit de extensiones (7.12-7.13).
"""El manifiesto de una extensión (`manifest.json` dentro del `.nyxext`; tarea 7.01).

Modelo pydantic estricto (HOJA-DE-RUTA §4.2): lo que no valide no se instala. Campos de más,
permisos inventados, un id raro o una API que no casa con la de Nyx: fuera.

Formas exactas de los permisos (HOJA-DE-RUTA §4.5; ninguno sirve para tocar un juego):

    net:<host>:<puerto>          conectar con ese servidor (p. ej. net:localhost:4455)
    files:read:<carpeta>         leer en una carpeta conocida (documentos, descargas…)
    files:write:<carpeta>        escribir en ella (a la papelera al borrar, como todo en Nyx)
    apps:launch                  abrir apps
    apps:control:<app>           usar app_action / ui_action en esa app
    audio · media                volumen y multimedia
    clipboard:read · clipboard:write
    notify · ui:panel            avisos y paneles de Nyx
    secrets                      claves en el Administrador de credenciales de Windows
    llm                          usar el cerebro de Nyx (con cupo)
    messages:<servicio>          mandar mensajes a otras personas (siempre rojo)

`ui:widget` (1.1) y `screen` (1.2) aún no existen: se rechazan.

`settings`: lo que el usuario tiene que darle a mano (la contraseña de OBS, un id de cliente…).
Se rellena en Ajustes → Extensiones, se guarda en el Administrador de credenciales y la
extensión lo lee con `nyx.ask("settings.get", {"key": ...})`. No hace falta permiso: solo ve
los suyos.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from nyx.tools.base import GamePolicy, Risk

#: La versión de la API de extensiones de Nyx (semántica: 1.x no rompe nada de 1.0).
NYX_API = (1, 0)

MANIFEST_NAME = "manifest.json"
MAX_MANIFEST_BYTES = 64 * 1024

Kind = Literal["actions", "tools", "shape", "mode", "preset", "knowledge", "personality"]

#: Carpetas del usuario que una extensión puede pedir por su nombre (nunca rutas libres).
KNOWN_FOLDERS = frozenset({"documentos", "descargas", "escritorio", "imagenes", "musica", "videos"})

_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,31}\.[a-z0-9][a-z0-9-]{1,47}$")
_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_NAME = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
_HOST = re.compile(
    r"^(?:localhost|(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}|\d{1,3}(?:\.\d{1,3}){3})$"
)
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
_API_TERM = re.compile(r"^(>=|>|<=|<|==)?(\d+)\.(\d+)$")

#: Permisos simples (sin parámetro).
_PLAIN = frozenset(
    {"apps:launch", "audio", "media", "clipboard:read", "clipboard:write", "notify", "ui:panel"}
    | {"secrets", "llm"}
)
#: Los que existirán más adelante: se nombran para decir por qué no valen.
_LATER = {"ui:widget": "1.1", "screen": "1.2"}

#: Riesgo mínimo de las herramientas que usan cada permiso (HOJA-DE-RUTA §4.5). SafetyGuard
#: aplica el mayor de los que use la herramienta, aunque la extensión declare menos.
_MIN_RISK = {
    "net": Risk.GREEN,
    "files:read": Risk.GREEN,
    "files:write": Risk.YELLOW,
    "apps:launch": Risk.GREEN,
    "apps:control": Risk.YELLOW,
    "audio": Risk.GREEN,
    "media": Risk.GREEN,
    "clipboard:read": Risk.GREEN,
    "clipboard:write": Risk.GREEN,
    "notify": Risk.GREEN,
    "ui:panel": Risk.GREEN,
    "secrets": Risk.GREEN,
    "llm": Risk.GREEN,
    "messages": Risk.RED,
}


@dataclass(frozen=True, slots=True)
class Permission:
    """Un permiso ya entendido. `kind` es la familia («net», «files:read»…) y `target` su
    parámetro («localhost:4455», «documentos», «discord»), o «» si no lleva."""

    kind: str
    target: str = ""

    def __str__(self) -> str:
        return f"{self.kind}:{self.target}" if self.target else self.kind

    @property
    def min_risk(self) -> Risk:
        return _MIN_RISK[self.kind]


class ManifestError(ValueError):
    """El manifiesto no vale. El mensaje es para personas (Ajustes y la línea de órdenes)."""


def parse_permission(text: str) -> Permission:
    if not isinstance(text, str) or text != text.strip() or not text:
        raise ValueError("permiso vacío o con espacios")
    if text in _PLAIN:
        return Permission(text)
    if text in _LATER:
        raise ValueError(f"«{text}» llegará en Nyx {_LATER[text]}")
    family, _, rest = text.partition(":")
    if family == "net":
        host, sep, port = rest.rpartition(":")
        if not sep or not _HOST.match(host) or not port.isdigit() or not 0 < int(port) < 65536:
            raise ValueError(f"«{text}»: tiene que ser net:<servidor>:<puerto>")
        return Permission("net", f"{host}:{int(port)}")
    if family == "files":
        mode, _, folder = rest.partition(":")
        if mode not in ("read", "write") or folder not in KNOWN_FOLDERS:
            folders = ", ".join(sorted(KNOWN_FOLDERS))
            raise ValueError(f"«{text}»: tiene que ser files:read|write:<{folders}>")
        return Permission(f"files:{mode}", folder)
    if family == "apps" and rest.startswith("control:"):
        app = rest.removeprefix("control:")
        if not _SLUG.match(app):
            raise ValueError(f"«{text}»: tiene que ser apps:control:<app>")
        return Permission("apps:control", app)
    if family == "messages":
        if not _SLUG.match(rest):
            raise ValueError(f"«{text}»: tiene que ser messages:<servicio>")
        return Permission("messages", rest)
    raise ValueError(f"«{text}» no es un permiso de Nyx")


def api_compatible(spec: str, api: tuple[int, int] = NYX_API) -> bool:
    """¿La API de Nyx cumple el rango del manifiesto («>=1.0 <2.0», «1.0», «>=1.2»)?"""
    terms = spec.split()
    if not terms:
        return False
    for term in terms:
        m = _API_TERM.match(term)
        if m is None:
            raise ValueError(f"«{spec}»: rango de versiones no válido")
        op, want = m.group(1) or "==", (int(m.group(2)), int(m.group(3)))
        ok = {
            ">=": api >= want,
            ">": api > want,
            "<=": api <= want,
            "<": api < want,
            "==": api == want,
        }[op]
        if not ok:
            return False
    return True


class License(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    type: Literal["free", "paid"] = "free"
    product: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9-]{0,47}$")
    #: Licencia del código (SPDX), p. ej. «MIT». La del SDK y los ejemplos es MIT.
    spdx: str = Field(default="", max_length=64, pattern=r"^[A-Za-z0-9.+\- ()]*$")

    @model_validator(mode="after")
    def _paid_needs_product(self) -> License:
        if self.type == "paid" and not self.product:
            raise ValueError("una extensión de pago necesita «product»")
        return self


Keyword = Annotated[str, Field(min_length=2, max_length=40)]
ToolName = Annotated[str, Field(pattern=_NAME.pattern)]


class Group(BaseModel):
    """Un grupo de herramientas para el selector (tools/groups.py; tarea 7.04)."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    name: str = Field(pattern=_NAME.pattern)
    about: str = Field(min_length=3, max_length=80)
    keywords: tuple[Keyword, ...] = Field(min_length=1, max_length=40)
    tools: tuple[ToolName, ...] = Field(min_length=1, max_length=20)


class Setting(BaseModel):
    """Un dato que el usuario da a la extensión en Ajustes (7.14)."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    label: str = Field(min_length=1, max_length=40)
    hint: str = Field(default="", max_length=160)
    #: Secreto: no se vuelve a enseñar una vez guardado (solo «guardada»).
    secret: bool = True


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    id: str = Field(pattern=_ID.pattern)
    name: str = Field(min_length=1, max_length=60)
    version: str = Field(pattern=_SEMVER.pattern)
    author: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=300)
    nyx_api: str = Field(min_length=1, max_length=40)
    kinds: tuple[Kind, ...] = Field(min_length=1)
    permissions: tuple[str, ...] = ()
    game_policy: dict[ToolName, GamePolicy] = Field(default_factory=dict)
    groups: tuple[Group, ...] = ()
    settings: tuple[Setting, ...] = Field(default=(), max_length=8)
    license: License = Field(default_factory=License)
    homepage: str = Field(default="", max_length=200, pattern=r"^(?:https://\S+)?$")

    @field_validator("kinds")
    @classmethod
    def _unique_kinds(cls, kinds: tuple[Kind, ...]) -> tuple[Kind, ...]:
        if len(set(kinds)) != len(kinds):
            raise ValueError("tipos repetidos")
        return kinds

    @field_validator("permissions")
    @classmethod
    def _valid_permissions(cls, permissions: tuple[str, ...]) -> tuple[str, ...]:
        parsed = [str(parse_permission(p)) for p in permissions]
        if len(set(parsed)) != len(parsed):
            raise ValueError("permisos repetidos")
        return tuple(parsed)

    @field_validator("nyx_api")
    @classmethod
    def _valid_api(cls, spec: str) -> str:
        api_compatible(spec)  # lanza si el rango está mal escrito
        return spec

    @model_validator(mode="after")
    def _coherent(self) -> Manifest:
        code = "tools" in self.kinds
        # Solo el código pide cosas a Nyx: lo demás (JSON, Markdown, formas) no ejecuta nada.
        if self.permissions and not code:
            raise ValueError("solo las extensiones con herramientas («tools») piden permisos")
        if (self.game_policy or self.groups or self.settings) and not code:
            raise ValueError(
                "«game_policy», «groups» y «settings» son para extensiones con herramientas"
            )
        keys = [s.key for s in self.settings]
        if len(set(keys)) != len(keys):
            raise ValueError("ajustes («settings») repetidos")
        return self

    @property
    def parsed_permissions(self) -> tuple[Permission, ...]:
        return tuple(parse_permission(p) for p in self.permissions)

    @property
    def major(self) -> int:
        return int(self.version.split(".")[0])

    def version_key(self) -> tuple[int, int, int]:
        major, minor, patch = (int(n) for n in self.version.split("."))
        return major, minor, patch

    def new_permissions(self, accepted: tuple[str, ...] | list[str]) -> tuple[str, ...]:
        """Los permisos que pide y aún no se han aceptado (una actualización que pide más)."""
        return tuple(p for p in self.permissions if p not in set(accepted))


def load_manifest(raw: bytes) -> Manifest:
    """El manifiesto validado, o `ManifestError` con lo que falla, en español."""
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ManifestError("el manifiesto es demasiado grande")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ManifestError(f"el manifiesto no es JSON válido: {e}") from e
    if not isinstance(data, dict):
        raise ManifestError("el manifiesto tiene que ser un objeto JSON")
    try:
        # Validar el JSON tal cual: en modo estricto acepta listas como tuplas y textos como
        # valores de enumeración, y nada más.
        manifest = Manifest.model_validate_json(raw)
    except ValidationError as e:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or 'manifiesto'}: {err['msg']}"
            for err in e.errors()
        )
        raise ManifestError(problems) from e
    if not api_compatible(manifest.nyx_api):
        api = ".".join(str(n) for n in NYX_API)
        raise ManifestError(f"necesita la API de Nyx «{manifest.nyx_api}» y esta es la {api}")
    return manifest
