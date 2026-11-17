"""Ajustes desde la ventana de Ajustes (SPEC sección 13): leer, cambiar y guardar.

La interfaz manda cambios parciales (`{"game": {"mode": "normal"}}`). Se validan con el
modelo, se guardan en settings.json y se copian **sobre el mismo objeto** de ajustes que usa
el resto del núcleo: así lo que lo lee en el momento (modo partida, políticas, listas de
juegos, responder en voz) cambia al instante sin reiniciar. Lo que solo se lee al arrancar
se devuelve en `restart` para que Ajustes diga «se aplica al reiniciar Nyx».

Solo se puede cambiar lo que tiene la ventana (EDITABLE): por ejemplo, la ruta de
whisper-server.exe o la dirección de Ollama no se tocan desde aquí. Al leerlos van también
los micrófonos y altavoces que hay, para elegirlos en Ajustes → Voz.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from nyx.bus import EventBus
from nyx.events import SettingsChanged, SettingsRequested
from nyx.settings.model import Settings, save_settings
from nyx.wake.custom import validate as validate_wake_phrase

log = logging.getLogger(__name__)

#: Lo que se puede cambiar desde Ajustes: secciones enteras (terminan en «.») o ajustes
#: concretos. Nada de rutas a programas ni direcciones de red.
EDITABLE: tuple[str, ...] = (
    "general.",
    "appearance.",
    "responses.",
    "game.",
    "wake.enabled",
    "wake.engine",
    "wake.sensitivity",
    "wake.custom_word",
    "wake.save_false_clips",
    "listen.followup_s",
    "listen.silence_ms",
    "tts.enabled",
    "tts.voice",
    "tts.speed",
    "audio.input_device",
    "audio.output_device",
    "llm.model",
    "llm.timeout_s",
    "onboarding.",
    "privacy.",
    "web.",
    "updates.",
    "extensions.dev_mode",
    "modes.",
)
#: Lo que solo se lee al arrancar: cambiarlo pide reiniciar Nyx.
NEEDS_RESTART: tuple[str, ...] = (
    "audio.",
    "wake.",
    "listen.",
    "stt.",
    "llm.",
    "tts.",
    "responses.tone",
)


class SettingsError(ValueError):
    """Cambio no válido: el mensaje se enseña tal cual en Ajustes."""


class SettingsService:
    def __init__(
        self,
        bus: EventBus,
        settings: Settings,
        path: Path | None = None,
        devices: Callable[[], tuple[list[str], list[str]]] | None = None,
    ) -> None:
        self.bus = bus
        self.settings = settings
        self.path = path
        # Micrófonos y altavoces (nombres), para Ajustes → Voz.
        self.devices = devices
        # Con lo que arrancó el núcleo: lo que se lee al arrancar solo cambia al reiniciar.
        self._started_with = self.snapshot()
        self._unsubscribe = bus.subscribe(SettingsRequested, self._on_request)

    def close(self) -> None:
        self._unsubscribe()

    def snapshot(self) -> dict[str, Any]:
        return self.settings.model_dump(mode="json")

    def apply(self, patch: Mapping[str, Any]) -> list[str]:
        """Aplica un cambio parcial. Devuelve lo que necesita reiniciar Nyx."""
        return apply_patch(self.settings, patch, self.path)

    def pending_restart(self) -> list[str]:
        """Lo que es distinto de cuando arrancó el núcleo y solo se aplica al reiniciar. Si se
        vuelve a dejar como estaba, deja de contar (y Ajustes quita el aviso)."""
        changed = _changed_paths(self._started_with, self.snapshot())
        return [p for p in changed if p.startswith(NEEDS_RESTART)]

    async def _on_request(self, event: SettingsRequested) -> None:
        error: str | None = None
        inputs: list[str] = []
        outputs: list[str] = []
        if event.patch is not None:
            try:
                self.apply(event.patch)
            except SettingsError as err:
                error = str(err)
                log.warning("Ajustes: %s", error)
        elif self.devices is not None:
            # Solo al leerlos (al abrir Ajustes): así salen los que se acaban de conectar.
            inputs, outputs = await asyncio.to_thread(self.devices)
        await self.bus.publish(
            SettingsChanged(
                data=self.snapshot(),
                restart=tuple(self.pending_restart()),
                error=error,
                inputs=tuple(inputs),
                outputs=tuple(outputs),
            )
        )


def apply_patch(
    settings: Settings, patch: Mapping[str, Any], path: Path | None = None
) -> list[str]:
    """Aplica un cambio parcial sobre `settings` (el mismo objeto que usa todo el núcleo) y lo
    guarda. Lo usan la ventana de Ajustes y «Nyx, baja la calidad del cristal» (nyx_control):
    las mismas validaciones y la misma lista de lo que se puede cambiar. Devuelve lo que
    necesita reiniciar Nyx."""
    before = settings.model_dump(mode="json")
    try:
        updated = Settings.model_validate(_merge(before, patch))
    except ValidationError as err:
        first = err.errors()[0]
        where = ".".join(str(p) for p in first["loc"])
        raise SettingsError(f"Valor no válido en {where}: {first['msg']}") from err
    changed = _changed_paths(before, updated.model_dump(mode="json"))
    blocked = [p for p in changed if not _editable(p)]
    if blocked:
        raise SettingsError(f"No se puede cambiar desde Ajustes: {', '.join(blocked)}")
    word = updated.wake.custom_word.strip()
    if "wake.custom_word" in changed and word:
        check = validate_wake_phrase(word)
        if not check.ok:
            raise SettingsError(f"La palabra «{word}» {'; '.join(check.problems)}")
    _copy_into(settings, updated)
    if changed:
        save_settings(settings, path)
        log.info("Ajustes cambiados: %s", ", ".join(changed))
    return [p for p in changed if p.startswith(NEEDS_RESTART)]


def _editable(path: str) -> bool:
    return any(path == e or (e.endswith(".") and path.startswith(e)) for e in EDITABLE)


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
