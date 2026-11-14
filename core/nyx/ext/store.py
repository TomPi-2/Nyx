"""Instalar, actualizar, desactivar y desinstalar extensiones (tarea 7.02).

- Cada versión en `%LOCALAPPDATA%\\Nyx\\extensions\\<id>\\<versión>\\`.
- El zip se abre con cuidado: sin rutas que salgan de su carpeta, sin enlaces, sin nombres
  reservados de Windows y con límites de tamaño y de archivos que se cuentan al descomprimir
  (no se fía de lo que dice la cabecera): un zip bomba no tumba a Nyx.
- El cambio de versión es atómico: la nueva se prepara aparte y el estado cambia de golpe (se
  escribe aparte y se sustituye). Si algo falla a medias, sigue la anterior.
- Desinstalar y las versiones viejas van a la papelera, como todo en Nyx (nunca borrado
  permanente).
- Estado en `%APPDATA%\\Nyx\\extensions.json`: versión activa, si está activada y los permisos
  aceptados. Una actualización que pide más permisos no se activa hasta que se acepten.

Instalar no ejecuta nada: solo copia y valida (las herramientas corren aparte, 7.06).
"""

from __future__ import annotations

import contextlib
import logging
import os
import re
import shutil
import stat
import threading
import uuid
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from nyx.ext.manifest import MANIFEST_NAME, Manifest, ManifestError, load_manifest
from nyx.paths import local_dir, roaming_dir

log = logging.getLogger(__name__)

PACKAGE_SUFFIX = ".nyxext"
MAX_FILES = 2_000
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_RATIO = 200  # más de 200:1 en un archivo de más de 1 MB huele a zip bomba
MAX_DEPTH = 12
_CHUNK = 1024 * 1024

_RESERVED = re.compile(r"^(?:con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\..*)?$", re.IGNORECASE)
_BAD_CHARS = re.compile(r'[<>:"|?*\\\x00-\x1f]')


class PackageError(ValueError):
    """El paquete no se puede instalar. El mensaje es para personas."""


class ExtState(BaseModel):
    """Lo que Nyx recuerda de una extensión instalada."""

    model_config = ConfigDict(extra="ignore")

    version: str
    enabled: bool = True
    accepted: list[str] = Field(default_factory=list)  # permisos aceptados
    #: Versión preparada que espera a que se acepten sus permisos nuevos (la activa sigue).
    pending: str | None = None
    dev: bool = False  # cargada sin firmar en modo desarrollador (7.08)


class StoreState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    version: int = 1
    extensions: dict[str, ExtState] = Field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Installed:
    manifest: Manifest
    path: Path
    state: ExtState

    @property
    def id(self) -> str:
        return self.manifest.id

    @property
    def active(self) -> bool:
        """Activada y con todos sus permisos aceptados."""
        return self.state.enabled and not self.manifest.new_permissions(self.state.accepted)


@dataclass(frozen=True, slots=True)
class InstallResult:
    status: Literal["installed", "updated", "needs_permissions"]
    manifest: Manifest
    #: Permisos que hay que aceptar antes de activarla (vacío si no hace falta nada).
    new_permissions: tuple[str, ...] = ()


def default_root() -> Path:
    return local_dir() / "extensions"


def default_state_path() -> Path:
    return roaming_dir() / "extensions.json"


def _trash(path: Path) -> None:
    from send2trash import send2trash

    send2trash(str(path))


def _safe_member(info: zipfile.ZipInfo) -> PurePosixPath | None:
    """La ruta relativa de una entrada, o None si es una carpeta. Lanza si es peligrosa."""
    name = info.filename
    if info.flag_bits & 0x1:
        raise PackageError(f"«{name}» está cifrado")
    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode):
        raise PackageError(f"«{name}» es un enlace")
    if "\\" in name or name.startswith("/") or _BAD_CHARS.search(name.replace("/", "")):
        raise PackageError(f"«{name}»: nombre de archivo no permitido")
    path = PurePosixPath(name)
    parts = path.parts
    if not parts or len(parts) > MAX_DEPTH:
        raise PackageError(f"«{name}»: ruta no permitida")
    for part in parts:
        if part in ("", ".", "..") or _RESERVED.match(part) or part != part.rstrip(". "):
            raise PackageError(f"«{name}»: ruta no permitida")
    return None if info.is_dir() else path


def read_package(package: Path) -> tuple[Manifest, list[tuple[zipfile.ZipInfo, PurePosixPath]]]:
    """Abre el `.nyxext`, comprueba todas sus entradas y valida el manifiesto (sin extraer)."""
    try:
        zf = zipfile.ZipFile(package)
    except (OSError, zipfile.BadZipFile) as e:
        raise PackageError(f"no es un paquete de extensión válido: {e}") from e
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_FILES:
            raise PackageError(f"tiene más de {MAX_FILES} archivos")
        members: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
        seen: set[str] = set()
        declared = 0
        for info in infos:
            path = _safe_member(info)
            if path is None:
                continue
            key = str(path).lower()  # Windows no distingue mayúsculas
            if key in seen:
                raise PackageError(f"«{path}» está repetido")
            seen.add(key)
            if info.file_size > MAX_FILE_BYTES:
                raise PackageError(f"«{path}» es demasiado grande")
            if info.file_size > _CHUNK and info.file_size > MAX_RATIO * max(info.compress_size, 1):
                raise PackageError(f"«{path}» se comprime demasiado (posible zip bomba)")
            declared += info.file_size
            if declared > MAX_TOTAL_BYTES:
                raise PackageError("el paquete descomprimido es demasiado grande")
            members.append((info, path))
        if MANIFEST_NAME.lower() not in seen:
            raise PackageError("no tiene manifest.json en la raíz")
        try:
            manifest = load_manifest(zf.read(MANIFEST_NAME))
        except KeyError as e:
            raise PackageError("no tiene manifest.json en la raíz") from e
        except ManifestError as e:
            raise PackageError(f"manifiesto no válido: {e}") from e
    return manifest, members


def _extract(package: Path, members: list[tuple[zipfile.ZipInfo, PurePosixPath]], to: Path) -> None:
    """Extrae contando bytes de verdad: la cabecera de un zip puede mentir."""
    total = 0
    root = to.resolve()
    with zipfile.ZipFile(package) as zf:
        for info, rel in members:
            target = (to / Path(*rel.parts)).resolve()
            if not target.is_relative_to(root):
                raise PackageError(f"«{rel}» sale de su carpeta")
            target.parent.mkdir(parents=True, exist_ok=True)
            written = 0
            with zf.open(info) as src, open(target, "xb") as dst:
                while chunk := src.read(_CHUNK):
                    written += len(chunk)
                    total += len(chunk)
                    if written > MAX_FILE_BYTES or written > max(info.file_size, 0) + _CHUNK:
                        raise PackageError(f"«{rel}» es más grande de lo que dice")
                    if total > MAX_TOTAL_BYTES:
                        raise PackageError("el paquete descomprimido es demasiado grande")
                    dst.write(chunk)


class ExtensionStore:
    """Las extensiones instaladas. Seguro entre hilos; las operaciones son de disco (llamar
    con `asyncio.to_thread` desde el bucle)."""

    def __init__(
        self,
        root: Path | None = None,
        state_path: Path | None = None,
        *,
        trash: Callable[[Path], None] = _trash,
    ) -> None:
        self.root = root or default_root()
        self.state_path = state_path or default_state_path()
        self._trash = trash
        self._lock = threading.RLock()
        self._state = self._load_state()

    # --- estado ---

    def _load_state(self) -> StoreState:
        try:
            return StoreState.model_validate_json(self.state_path.read_bytes())
        except FileNotFoundError:
            return StoreState()
        except ValueError:
            # Dañado: se empieza vacío sin sobrescribirlo hasta el próximo cambio (y se guarda
            # una copia para no perder nada).
            log.warning("extensions.json dañado: se ignora (copia en .dañado)")
            with contextlib.suppress(OSError):
                shutil.copy2(self.state_path, self.state_path.with_suffix(".json.dañado"))
            return StoreState()

    def _save(self) -> None:
        """Escribe aparte y sustituye de golpe: un corte de luz deja el anterior o el nuevo."""
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(f".{uuid.uuid4().hex}.tmp")
        tmp.write_text(self._state.model_dump_json(indent=2), encoding="utf-8")
        os.replace(tmp, self.state_path)

    # --- consultas ---

    def _folder(self, ext_id: str, version: str) -> Path:
        return self.root / ext_id / version

    def get(self, ext_id: str) -> Installed | None:
        with self._lock:
            state = self._state.extensions.get(ext_id)
            if state is None:
                return None
            folder = self._folder(ext_id, state.version)
            try:
                manifest = load_manifest((folder / MANIFEST_NAME).read_bytes())
            except (OSError, ManifestError):
                log.warning("Extensión %s dañada en disco: se ignora", ext_id)
                return None
            return Installed(manifest, folder, state.model_copy())

    def installed(self) -> list[Installed]:
        with self._lock:
            ids = sorted(self._state.extensions)
        return [found for ext_id in ids if (found := self.get(ext_id)) is not None]

    def pending_manifest(self, ext_id: str) -> Manifest | None:
        """El manifiesto de la actualización que espera a que se acepten sus permisos."""
        with self._lock:
            state = self._state.extensions.get(ext_id)
            if state is None or not state.pending:
                return None
            try:
                raw = (self._folder(ext_id, state.pending) / MANIFEST_NAME).read_bytes()
                return load_manifest(raw)
            except (OSError, ManifestError):
                return None

    def active(self) -> list[Installed]:
        return [ext for ext in self.installed() if ext.active]

    # --- instalar y actualizar ---

    def install(self, package: Path, *, accept: bool = False, dev: bool = False) -> InstallResult:
        """Instala o actualiza desde un `.nyxext`.

        `accept`: el usuario ya ha visto y aceptado los permisos que pide (Ajustes enseña
        `read_package(...)[0].permissions` antes de llamar). Sin aceptar, una extensión nueva
        queda instalada pero desactivada; una actualización con permisos nuevos se prepara y
        la versión anterior sigue funcionando hasta que se acepten.
        """
        manifest, members = read_package(package)
        with self._lock:
            current = self._state.extensions.get(manifest.id)
            if current is not None and _key(manifest.version) < _key(current.version):
                raise PackageError(
                    f"ya tienes la versión {current.version}, más nueva que la {manifest.version}"
                )
            staging = self.root / manifest.id / f".{manifest.version}.{uuid.uuid4().hex}.tmp"
            try:
                staging.mkdir(parents=True)
                _extract(package, members, staging)
                # Lo extraído tiene que ser lo mismo que se validó.
                if load_manifest((staging / MANIFEST_NAME).read_bytes()) != manifest:
                    raise PackageError("el manifiesto cambió al extraerlo")
                final = self._folder(manifest.id, manifest.version)
                if final.exists():
                    # Reinstalar la misma versión: la que hay se aparta y solo se tira cuando
                    # la nueva ya está en su sitio (si el cambio falla, vuelve).
                    old = final.with_name(f".{manifest.version}.{uuid.uuid4().hex}.old")
                    os.replace(final, old)
                    try:
                        os.replace(staging, final)
                    except OSError:
                        os.replace(old, final)
                        raise
                    self._trash_quietly(old)
                else:
                    os.replace(staging, final)
            except BaseException:
                self._trash_quietly(staging)
                raise
            return self._switch(manifest, current, accept=accept, dev=dev)

    def _switch(
        self, manifest: Manifest, current: ExtState | None, *, accept: bool, dev: bool
    ) -> InstallResult:
        if current is None:
            accepted = list(manifest.permissions) if accept else []
            self._state.extensions[manifest.id] = ExtState(
                version=manifest.version, enabled=accept, accepted=accepted, dev=dev
            )
            self._save()
            needs = () if accept else manifest.permissions
            return InstallResult("needs_permissions" if needs else "installed", manifest, needs)
        new = manifest.new_permissions(current.accepted)
        if new and not accept:
            # Se queda preparada: la anterior sigue activa con lo que ya tenía.
            old_pending = current.pending
            current.pending = manifest.version
            self._save()
            if old_pending and old_pending not in (manifest.version, current.version):
                self._trash_quietly(self._folder(manifest.id, old_pending))
            return InstallResult("needs_permissions", manifest, new)
        return self._activate(manifest, current, dev=dev)

    def _activate(self, manifest: Manifest, current: ExtState, *, dev: bool) -> InstallResult:
        old = current.version
        accepted = sorted(set(current.accepted) | set(manifest.permissions))
        self._state.extensions[manifest.id] = ExtState(
            version=manifest.version,
            enabled=current.enabled,
            accepted=accepted,
            dev=dev,
        )
        self._save()  # aquí cambia de versión, de golpe
        if old != manifest.version:
            self._trash_quietly(self._folder(manifest.id, old))
        if current.pending and current.pending != manifest.version:
            self._trash_quietly(self._folder(manifest.id, current.pending))
        return InstallResult("updated", manifest)

    def accept_permissions(self, ext_id: str) -> Installed:
        """El usuario acepta lo que pide: se activa la versión preparada (o la nueva)."""
        with self._lock:
            current = self._state.extensions.get(ext_id)
            if current is None:
                raise PackageError("esa extensión no está instalada")
            version = current.pending or current.version
            manifest = load_manifest((self._folder(ext_id, version) / MANIFEST_NAME).read_bytes())
            if current.pending:
                current.pending = None
                self._activate(manifest, current, dev=current.dev)
                current = self._state.extensions[ext_id]
            current.accepted = sorted(set(current.accepted) | set(manifest.permissions))
            current.enabled = True
            self._save()
        found = self.get(ext_id)
        assert found is not None
        return found

    def set_enabled(self, ext_id: str, enabled: bool) -> None:
        with self._lock:
            current = self._state.extensions.get(ext_id)
            if current is None:
                raise PackageError("esa extensión no está instalada")
            current.enabled = enabled
            self._save()

    def uninstall(self, ext_id: str) -> None:
        """Fuera del estado y su carpeta a la papelera."""
        with self._lock:
            if self._state.extensions.pop(ext_id, None) is None:
                raise PackageError("esa extensión no está instalada")
            self._save()
            self._trash_quietly(self.root / ext_id)

    def _trash_quietly(self, path: Path) -> None:
        if not path.exists():
            return
        try:
            self._trash(path)
        except OSError:
            log.warning("No se pudo mandar a la papelera %s", path, exc_info=True)


def _key(version: str) -> tuple[int, ...]:
    return tuple(int(n) for n in version.split("."))
