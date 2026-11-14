"""Extensiones en marcha: cargar lo que traen las activas y aplicarlo sin reiniciar (7.04).

Al instalar, actualizar, activar, desactivar o desinstalar, el gestor vuelve a leer las activas
y aplica:

- las acciones por app (`app_catalog.set_extension_profiles`),
- el conocimiento (`nyx_info`, marcado como externo),
- las herramientas y sus grupos: el registro las añade o las quita por extensión y se hace un
  selector nuevo con los grupos de Nyx y los de las extensiones.

Cambiar las herramientas cambia el prefijo del modelo y su caché: se recalienta en ese momento
(`apply_selector`), **nunca en partida**. Si se está jugando, el cambio espera a que acabe
(`game_ended`). Las herramientas con código las crea `tool_factory` (el host de 7.06/7.07);
sin él, solo se carga lo que no tiene código.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nyx.brain.select import ToolSelector, _chars
from nyx.ext.content import ExtContent, Personality, Preset, load_content
from nyx.ext.store import ExtensionStore, Installed, InstallResult
from nyx.index.aliases import normalize
from nyx.tools import app_catalog, nyx_info
from nyx.tools.base import Tool
from nyx.tools.groups import GROUPS, MAX_GROUP_CHARS, Group
from nyx.tools.registry import ToolRegistry

log = logging.getLogger(__name__)

ToolFactory = Callable[[Installed], list[Tool[Any]]]
ApplySelector = Callable[[ToolSelector], Awaitable[None]]


@dataclass(slots=True)
class ExtStatus:
    """Lo que Ajustes enseña de cada extensión."""

    id: str
    name: str
    version: str
    author: str
    description: str
    enabled: bool
    active: bool
    dev: bool
    permissions: tuple[str, ...]
    pending_permissions: tuple[str, ...]
    problems: list[str] = field(default_factory=list)


class ExtensionManager:
    def __init__(
        self,
        store: ExtensionStore,
        registry: ToolRegistry,
        *,
        budget_chars: int,
        apply_selector: ApplySelector,
        playing: Callable[[], bool] = lambda: False,
        tool_factory: ToolFactory | None = None,
    ) -> None:
        self.store = store
        self.registry = registry
        self.budget_chars = budget_chars
        self._apply_selector = apply_selector
        self._playing = playing
        self._tool_factory = tool_factory
        self._lock = asyncio.Lock()
        self._pending = False  # hay un cambio esperando a que acabe la partida
        self.problems: dict[str, list[str]] = {}
        self.presets: dict[str, Preset] = {}  # «id/nombre» → preajuste
        self.personalities: dict[str, Personality] = {}
        self.groups: tuple[Group, ...] = ()  # los de las extensiones

    # --- operaciones (Ajustes) ---

    async def install(
        self, package: Path, *, accept: bool = False, dev: bool = False
    ) -> InstallResult:
        result = await asyncio.to_thread(self.store.install, package, accept=accept, dev=dev)
        await self.reload()
        return result

    async def accept_permissions(self, ext_id: str) -> None:
        await asyncio.to_thread(self.store.accept_permissions, ext_id)
        await self.reload()

    async def set_enabled(self, ext_id: str, enabled: bool) -> None:
        await asyncio.to_thread(self.store.set_enabled, ext_id, enabled)
        await self.reload()

    async def uninstall(self, ext_id: str) -> None:
        await asyncio.to_thread(self.store.uninstall, ext_id)
        await self.reload()

    async def game_ended(self) -> None:
        """Al acabar la partida se aplica lo que esperaba."""
        if self._pending:
            await self.reload()

    # --- cargar ---

    async def reload(self) -> None:
        async with self._lock:
            if self._playing():
                # Cambiaría el prefijo del modelo en mitad de la partida: después.
                self._pending = True
                log.info("Extensiones: cambio pendiente hasta que acabe la partida")
                return
            self._pending = False
            active = await asyncio.to_thread(self.store.active)
            contents = await asyncio.to_thread(
                lambda: [(ext, load_content(ext.manifest, ext.path)) for ext in active]
            )
            self.problems = {ext.id: list(content.problems) for ext, content in contents}
            self._apply_content(contents)
            self._apply_tools(active)
            selector = ToolSelector(
                self.registry, groups=(*GROUPS, *self.groups), budget_chars=self.budget_chars
            )
            log.info(
                "Extensiones activas: %s (%d herramientas de extensiones; todas caben: %s)",
                ", ".join(ext.id for ext in active) or "ninguna",
                sum(1 for t in self.registry.all() if self.registry.owner_of(t.name)),
                "sí" if selector.all_fit else "no",
            )
        await self._apply_selector(selector)

    def _apply_content(self, contents: list[tuple[Installed, ExtContent]]) -> None:
        profiles = []
        knowledge: dict[str, tuple[str, str]] = {}
        self.presets, self.personalities = {}, {}
        for ext, content in contents:
            profiles += content.profiles
            for title, text in content.knowledge.items():
                knowledge[title] = (ext.manifest.name, text)
            for stem, preset in content.presets.items():
                self.presets[f"{ext.id}/{stem}"] = preset
            if content.personality is not None:
                self.personalities[ext.id] = content.personality
        app_catalog.set_extension_profiles(profiles)
        nyx_info.set_extension_knowledge(knowledge)

    def _apply_tools(self, active: list[Installed]) -> None:
        for owner in self.registry.owners():
            self.registry.unregister_owner(owner)
        groups: list[Group] = []
        if self._tool_factory is None:
            self.groups = ()
            return
        for ext in active:
            if "tools" not in ext.manifest.kinds:
                continue
            try:
                tools = self._tool_factory(ext)
            except Exception as e:  # una extensión rota no tumba a Nyx
                log.warning(
                    "Extensión %s: no se pudieron cargar sus herramientas", ext.id, exc_info=True
                )
                self.problems.setdefault(ext.id, []).append(f"herramientas: {e}")
                continue
            clash = [t.name for t in tools if self.registry.get(t.name) is not None]
            if clash:
                self.problems.setdefault(ext.id, []).append(
                    f"herramientas con el nombre de otra: {', '.join(clash)}"
                )
                continue
            for tool in tools:
                self.registry.register(tool, owner=ext.id)
            groups += self._groups_of(ext, {t.name for t in tools})
        self.groups = tuple(groups)

    def _groups_of(self, ext: Installed, names: set[str]) -> list[Group]:
        out = []
        taken = {g.name for g in GROUPS}
        for spec in ext.manifest.groups:
            tools = tuple(n for n in spec.tools if n in names)
            if not tools:
                continue
            size = sum(_chars(t.schema()) for n in tools if (t := self.registry.get(n)))
            if size > MAX_GROUP_CHARS:
                self.problems.setdefault(ext.id, []).append(
                    f"el grupo «{spec.name}» es demasiado grande: pártelo"
                )
                continue
            name = spec.name if spec.name not in taken else f"{ext.id}.{spec.name}"
            taken.add(name)
            # Palabras clave literales (las de Nyx son trozos de regex; las de fuera, no).
            keywords = tuple(
                re.escape(k) for k in dict.fromkeys(normalize(k) for k in spec.keywords) if k
            )
            out.append(Group(name, spec.about, tools, keywords))
        return out

    # --- consultas ---

    def status(self) -> list[ExtStatus]:
        out = []
        for ext in self.store.installed():
            pending: tuple[str, ...] = ()
            if ext.state.pending:
                found = self.store.pending_manifest(ext.id)
                pending = found.new_permissions(ext.state.accepted) if found else ()
            else:
                pending = ext.manifest.new_permissions(ext.state.accepted)
            m = ext.manifest
            out.append(
                ExtStatus(
                    id=m.id,
                    name=m.name,
                    version=m.version,
                    author=m.author,
                    description=m.description,
                    enabled=ext.state.enabled,
                    active=ext.active,
                    dev=ext.state.dev,
                    permissions=m.permissions,
                    pending_permissions=pending,
                    problems=self.problems.get(m.id, []),
                )
            )
        return out
