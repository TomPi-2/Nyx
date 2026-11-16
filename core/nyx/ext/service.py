"""Ajustes → Extensiones, la parte del núcleo (tarea 7.11).

Atiende lo que pide la ventana (`ExtRequested`) y contesta siempre con el estado completo
(`ExtStatusChanged`): las instaladas, si está el modo desarrollador y, al elegir un paquete,
lo que trae antes de instalarlo (nombre, autor, permisos y si lo firma Tepnyx).

Instalar exige la firma de Tepnyx salvo con el modo desarrollador (`extensions.dev_mode`); en
ese caso queda «sin revisar». Instalar solo se hace después de enseñar los permisos (la
ventana manda `install` cuando el usuario ha pulsado «Instalar» en la vista de `inspect`).

Con el modo desarrollador también se puede cargar una carpeta (7.16, «Cargar una carpeta»):
se empaqueta en `%LOCALAPPDATA%\\Nyx\\ext-dev\\cargadas` con las mismas comprobaciones que un
paquete y sigue el mismo camino (ver lo que trae, aceptar, instalar). Nyx recuerda la carpeta
de cada extensión cargada para «Recargar» tras cambiar el código.

Los ajustes de cada extensión (`settings` del manifiesto: la contraseña de OBS…) se guardan en
el Administrador de credenciales (`api.write_setting`). Los secretos no vuelven a la ventana:
solo si están puestos.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from nyx.bus import EventBus
from nyx.events import ExtRequested, ExtStatusChanged
from nyx.ext import api, official
from nyx.ext.manager import ExtensionManager
from nyx.ext.signing import SignatureError, verify_package
from nyx.ext.store import PACKAGE_SUFFIX, PackageError, read_package
from nyx.paths import local_dir
from nyx.settings.model import Settings

log = logging.getLogger(__name__)


class ExtensionsService:
    def __init__(
        self,
        bus: EventBus,
        manager: ExtensionManager,
        settings: Settings,
        *,
        read_setting: Callable[[str, str], str | None] = api.read_setting,
        write_setting: Callable[[str, str, str], None] = api.write_setting,
        official_packages: Callable[[], list[Path]] = official.packages,
        dev_dir: Path | None = None,
    ) -> None:
        self.bus = bus
        self.manager = manager
        self.settings = settings
        self._read_setting = read_setting
        self._write_setting = write_setting
        self._official_packages = official_packages
        self._dev_dir = dev_dir or local_dir() / "ext-dev"
        self._unsubscribe = bus.subscribe(ExtRequested, self._on_request)

    def close(self) -> None:
        self._unsubscribe()

    async def _on_request(self, req: ExtRequested) -> None:
        inspect: dict[str, Any] | None = None
        error: str | None = None
        try:
            if req.action == "inspect":
                inspect = await asyncio.to_thread(self._inspect, Path(req.path))
            elif req.action == "install":
                await self._install(Path(req.path))
            elif req.action == "accept":
                await self.manager.accept_permissions(req.ext_id)
            elif req.action in ("enable", "disable"):
                await self.manager.set_enabled(req.ext_id, req.action == "enable")
            elif req.action == "uninstall":
                await self.manager.uninstall(req.ext_id)
            elif req.action == "setting":
                await self._set(req.ext_id, req.key, req.value)
        except (PackageError, OSError, ValueError) as e:
            log.info("Extensiones (%s): %s", req.action, e)
            error = str(e)
        await self.publish(inspect=inspect, error=error)

    async def publish(
        self, *, inspect: dict[str, Any] | None = None, error: str | None = None
    ) -> None:
        items = await asyncio.to_thread(self._items)
        offers = await asyncio.to_thread(self._official)
        await self.bus.publish(
            ExtStatusChanged(items, self.settings.extensions.dev_mode, inspect, error, offers)
        )

    def _items(self) -> list[dict[str, Any]]:
        items = []
        folders = self._folders()
        for status in self.manager.status():
            item = asdict(status)
            item["folder"] = folders.get(status.id) if status.dev else None
            ext = self.manager.store.get(status.id)
            item["settings"] = []
            for s in ext.manifest.settings if ext is not None else ():
                try:
                    value = self._read_setting(status.id, s.key)
                except Exception as e:  # el Administrador de credenciales no contesta
                    log.warning("No se pudo leer un ajuste de %s: %s", status.id, e)
                    value = None
                item["settings"].append(
                    {
                        "key": s.key,
                        "label": s.label,
                        "hint": s.hint,
                        "secret": s.secret,
                        "set": bool(value),
                        # Un secreto nunca vuelve a la ventana.
                        "value": None if s.secret else (value or ""),
                    }
                )
            items.append(item)
        return items

    def _official(self) -> list[dict[str, Any]]:
        """Las oficiales que vienen con Nyx y no tienes (o tienes en una versión más vieja)."""
        out = []
        for path in self._official_packages():
            try:
                manifest, _ = read_package(path)
            except (PackageError, OSError) as e:
                log.warning("Extensión oficial %s: %s", path.name, e)
                continue
            current = self.manager.store.get(manifest.id)
            if current is not None and current.manifest.version_key() >= manifest.version_key():
                continue
            out.append(
                {
                    "path": str(path),
                    "id": manifest.id,
                    "name": manifest.name,
                    "description": manifest.description,
                    "version": manifest.version,
                    "update": current is not None,
                }
            )
        return out

    async def _set(self, ext_id: str, key: str, value: str) -> None:
        ext = self.manager.store.get(ext_id)
        if ext is None or key not in {s.key for s in ext.manifest.settings}:
            raise ValueError("esa extensión no tiene ese ajuste")
        await asyncio.to_thread(self._write_setting, ext_id, key, value.strip())

    def _folders(self) -> dict[str, str]:
        """De qué carpeta salió cada extensión cargada (para «Recargar»)."""
        try:
            data = json.loads((self._dev_dir / "carpetas.json").read_text(encoding="utf-8"))
        except OSError, ValueError:
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(k): str(v) for k, v in data.items()}

    def _remember_folder(self, ext_id: str, folder: Path) -> None:
        folders = self._folders()
        folders[ext_id] = str(folder)
        self._dev_dir.mkdir(parents=True, exist_ok=True)
        (self._dev_dir / "carpetas.json").write_text(
            json.dumps(folders, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _package(self, path: Path) -> Path:
        if path.is_dir():
            # «Cargar una carpeta»: solo para quien hace extensiones (modo desarrollador).
            if not self.settings.extensions.dev_mode:
                raise PackageError("cargar una carpeta solo se puede con el modo desarrollador")
            out = self._dev_dir / "cargadas" / f"{path.name}{PACKAGE_SUFFIX}"
            out.parent.mkdir(parents=True, exist_ok=True)
            return official.pack_folder(path, out)
        if path.suffix.lower() != PACKAGE_SUFFIX or not path.is_file():
            raise PackageError(
                f"elige un archivo {PACKAGE_SUFFIX} o, en modo desarrollador, una carpeta"
            )
        return path

    def _inspect(self, path: Path) -> dict[str, Any]:
        """Lo que trae un paquete (o una carpeta, ya empaquetada), sin instalar nada."""
        source = path
        path = self._package(path)
        manifest, members = read_package(path)
        try:
            verify_package(path, [m for _, m in members], self.manager.store.trusted)
            signed = True
        except SignatureError:
            signed = False
        current = self.manager.store.get(manifest.id)
        return {
            "path": str(path),
            "id": manifest.id,
            "name": manifest.name,
            "author": manifest.author,
            "version": manifest.version,
            "description": manifest.description,
            "kinds": list(manifest.kinds),
            "permissions": list(manifest.permissions),
            # Los delicados, con su porqué: sin la aprobación de Tepnyx, solo en desarrollo.
            "restricted": list(manifest.restricted),
            "why": dict(manifest.why),
            "folder": str(source) if source.is_dir() else None,
            "signed": signed,
            "installable": signed or self.settings.extensions.dev_mode,
            "installed_version": current.manifest.version if current else None,
        }

    async def _install(self, path: Path) -> None:
        info = await asyncio.to_thread(self._inspect, path)
        if not info["installable"]:
            raise PackageError("no está firmada por Tepnyx: solo con el modo desarrollador")
        # El usuario ya ha visto los permisos (vista de `inspect`): se aceptan al instalar.
        await self.manager.install(Path(info["path"]), accept=True, dev=not info["signed"])
        if info["folder"]:
            await asyncio.to_thread(self._remember_folder, info["id"], Path(info["folder"]))
