"""Ajustes desde la ventana de Ajustes (SPEC sección 13): leer, cambiar y guardar.

La interfaz manda cambios parciales (`{"game": {"mode": "normal"}}`). Se validan con el
modelo, se guardan en settings.json y se copian **sobre el mismo objeto** de ajustes que usa
el resto del núcleo: así lo que lo lee en el momento (modo partida, políticas, listas de
juegos, responder en voz) cambia al instante sin reiniciar. Lo que solo se lee al arrancar
se devuelve en `restart` para que Ajustes diga «se aplica al reiniciar Nyx».

Solo se pueden cambiar las secciones que tiene la ventana (EDITABLE): por ejemplo, la ruta de
whisper-server.exe no se toca desde aquí.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from nyx.bus import EventBus
from nyx.events import SettingsChanged, SettingsRequested
from nyx.settings.model import Settings, save_settings

log = logging.getLogger(__name__)

#: Secciones que se pueden cambiar desde Ajustes (5c‑1). Se amplía en 5c‑2.
EDITABLE = frozenset({"appearance", "responses", "game"})
#: Lo que solo se lee al arrancar: cambiarlo pide reiniciar Nyx.
NEEDS_RESTART: tuple[str, ...] = ("audio.", "wake.", "listen.", "stt.", "llm.", "tts.")


class SettingsError(ValueError):
    """Cambio no válido: el mensaje se enseña tal cual en Ajustes."""


class SettingsService:
    def __init__(self, bus: EventBus, settings: Settings, path: Path | None = None) -> None:
        self.bus = bus
        self.settings = settings
        self.path = path
        self._unsubscribe = bus.subscribe(SettingsRequested, self._on_request)

    def close(self) -> None:
        self._unsubscribe()

    def snapshot(self) -> dict[str, Any]:
        return self.settings.model_dump(mode="json")

    def apply(self, patch: Mapping[str, Any]) -> list[str]:
        """Aplica un cambio parcial. Devuelve lo que necesita reiniciar Nyx."""
        unknown = set(patch) - EDITABLE
        if unknown:
            raise SettingsError(f"No se puede cambiar desde Ajustes: {', '.join(sorted(unknown))}")
        before = self.snapshot()
        try:
            updated = Settings.model_validate(_merge(before, patch))
        except ValidationError as err:
            first = err.errors()[0]
            where = ".".join(str(p) for p in first["loc"])
            raise SettingsError(f"Valor no válido en {where}: {first['msg']}") from err
        _copy_into(self.settings, updated)
        after = self.snapshot()
        changed = _changed_paths(before, after)
        if changed:
            save_settings(self.settings, self.path)
            log.info("Ajustes cambiados: %s", ", ".join(changed))
        return [p for p in changed if p.startswith(NEEDS_RESTART)]

    async def _on_request(self, event: SettingsRequested) -> None:
        restart: list[str] = []
        error: str | None = None
        if event.patch is not None:
            try:
                restart = self.apply(event.patch)
            except SettingsError as err:
                error = str(err)
                log.warning("Ajustes: %s", error)
        await self.bus.publish(
            SettingsChanged(data=self.snapshot(), restart=tuple(restart), error=error)
        )


#: Diccionarios que son valores en sí (se sustituyen enteros, no se mezclan): así quitar una
#: política la devuelve a su valor por defecto.
REPLACE_WHOLE = frozenset({"policies"})


def _merge(base: Mapping[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
    """Mezcla recursiva: las secciones se combinan; el resto se sustituye."""
    out = dict(base)
    for key, value in patch.items():
        current = out.get(key)
        if key in REPLACE_WHOLE:
            out[key] = value
        elif isinstance(value, Mapping) and isinstance(current, Mapping):
            out[key] = _merge(current, value)
        else:
            out[key] = value
    return out


def _copy_into(dst: BaseModel, src: BaseModel) -> None:
    """Copia `src` sobre `dst` sin cambiar los objetos que otros ya tienen: las secciones,
    las listas y los diccionarios se actualizan por dentro."""
    for name in type(src).model_fields:
        new = getattr(src, name)
        old = getattr(dst, name)
        if isinstance(old, BaseModel) and isinstance(new, BaseModel):
            _copy_into(old, new)
        elif isinstance(old, list) and isinstance(new, list):
            old[:] = new
        elif isinstance(old, dict) and isinstance(new, dict):
            old.clear()
            old.update(new)
        elif old != new:
            setattr(dst, name, new)


def _changed_paths(
    before: Mapping[str, Any], after: Mapping[str, Any], prefix: str = ""
) -> list[str]:
    paths: list[str] = []
    for key in sorted(set(before) | set(after)):
        a, b = before.get(key), after.get(key)
        path = f"{prefix}{key}"
        if isinstance(a, Mapping) and isinstance(b, Mapping) and key not in REPLACE_WHOLE:
            paths.extend(_changed_paths(a, b, f"{path}."))
        elif a != b:
            paths.append(path)
    return paths
