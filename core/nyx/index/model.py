"""Entradas de la caché del sistema (SPEC sección 10)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Kind(StrEnum):
    APP = "app"
    GAME = "game"
    FOLDER = "folder"
    SETTING = "setting"  # página de Configuración (ms-settings:)
    WEB = "web"


class LaunchKind(StrEnum):
    APPS_FOLDER = "appsfolder"  # shell:AppsFolder\<AppID>: apps de escritorio y de la Store
    URI = "uri"  # https://, steam://, ms-settings:, com.epicgames.launcher://…
    EXE = "exe"  # ejecutable con argumentos (Riot Client)
    PATH = "path"  # carpeta o archivo


@dataclass(frozen=True, slots=True)
class Launch:
    kind: LaunchKind
    value: str
    args: tuple[str, ...] = ()

    def to_json(self) -> str:
        return json.dumps({"kind": self.kind, "value": self.value, "args": list(self.args)})

    @classmethod
    def from_json(cls, raw: str) -> Launch:
        data: dict[str, Any] = json.loads(raw)
        return cls(LaunchKind(data["kind"]), str(data["value"]), tuple(data.get("args", ())))


@dataclass(frozen=True, slots=True)
class Entry:
    """Algo que se puede abrir por su nombre."""

    key: str  # estable entre escaneos: conserva el uso y los alias del usuario
    kind: Kind
    name: str
    launch: Launch
    source: str
    process: str | None = None  # ejecutable en minúsculas, para encontrar sus ventanas
    aliases: tuple[str, ...] = field(default=())
