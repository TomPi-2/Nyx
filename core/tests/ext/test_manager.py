"""7.04: herramientas, grupos, acciones y conocimiento de las extensiones en caliente, sin
reiniciar Nyx; el prefijo del modelo se recalienta al cambiar, nunca en partida."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from nyx.brain.select import ToolSelector
from nyx.ext.manager import ExtensionManager
from nyx.ext.store import ExtensionStore, Installed
from nyx.tools import app_catalog, nyx_info
from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult
from nyx.tools.registry import ToolRegistry, default_registry
from tests.ext.conftest import TRUSTED, code_files, signed


class Scene(Params):
    name: str = ""


def fake_tool(tool_name: str) -> Tool[Any]:
    class Fake(Tool[Scene]):
        name = tool_name
        description = "Cambia de escena en OBS."
        risk = Risk.GREEN
        game_policy = GamePolicy.ALLOWED
        category = Category.APPS
        params_model = Scene

        async def run(self, params: Scene, ctx: ToolContext) -> ToolResult:
            return ToolResult(ok=True, message="hecho")

    return Fake()


def package(tmp: Path, ext_id: str = "alguien.obs", **changes: Any) -> Path:
    manifest = {
        "id": ext_id,
        "name": "OBS",
        "version": "1.0.0",
        "author": "Alguien",
        "nyx_api": "1.0",
        "kinds": ["tools", "actions", "knowledge"],
        "permissions": ["net:localhost:4455"],
        "groups": [
            {"name": "obs", "about": "OBS", "keywords": ["obs", "escena"], "tools": ["obs_scene"]}
        ],
        **changes,
    }
    actions = {
        "apps": [
            {
                "name": "OBS Studio",
                "processes": ["obs64.exe"],
                "actions": {"start_recording": {"label": "Grabar", "keys": "ctrl+f9"}},
            }
        ]
    }
    path = tmp / f"{ext_id}.nyxext"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("actions.json", json.dumps(actions))
        zf.writestr("knowledge/obs.md", "## Escenas\n\nUna escena es un conjunto de fuentes.")
        if "tools" in manifest["kinds"]:
            for member, blob in code_files("obs_scene").items():
                zf.writestr(member, blob)
    return signed(path)


class Harness:
    def __init__(self, tmp: Path, *, factory: Any = None) -> None:
        self.registry = default_registry()
        self.store = ExtensionStore(
            tmp / "ext", tmp / "extensions.json", trash=lambda p: None, trusted_keys=TRUSTED
        )
        self.applied: list[ToolSelector] = []
        self.playing = False

        async def apply(selector: ToolSelector) -> None:
            self.applied.append(selector)

        self.manager = ExtensionManager(
            self.store,
            self.registry,
            budget_chars=27033,
            apply_selector=apply,
            playing=lambda: self.playing,
            tool_factory=factory or (lambda ext: [fake_tool("obs_scene")]),
        )


@pytest.fixture(autouse=True)
def clean_globals() -> Any:
    yield
    app_catalog.set_extension_profiles([])
    nyx_info.set_extension_knowledge({})


async def test_install_brings_everything_without_restarting(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    await h.manager.install(package(tmp_path), accept=True)
    assert h.registry.get("obs_scene") is not None
    assert h.registry.owner_of("obs_scene") == "alguien.obs"
    assert [g.name for g in h.manager.groups] == ["obs"]
    # Selector nuevo con el grupo de la extensión, y aplicado (recalentar).
    selector = h.applied[-1]
    assert "obs" in selector.groups_for("cambia de escena en obs")
    # Las acciones y el conocimiento también.
    assert app_catalog.profile_for("obs64.exe") is not None
    found = await nyx_info.NyxInfo().run(nyx_info.NyxInfoParams(topic="obs escenas"), None)  # type: ignore[arg-type]
    assert found.external is not None and "fuentes" in found.external  # como algo de fuera


async def test_uninstall_takes_it_all_away(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    await h.manager.install(package(tmp_path), accept=True)
    await h.manager.uninstall("alguien.obs")
    assert h.registry.get("obs_scene") is None
    assert h.manager.groups == ()
    assert app_catalog.profile_for("obs64.exe") is None
    # La lista vuelve a ser la de Nyx (misma caché que sin extensiones).
    assert h.applied[-1].names == frozenset(t.name for t in default_registry().all())


async def test_disable_and_enable(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    await h.manager.install(package(tmp_path), accept=True)
    await h.manager.set_enabled("alguien.obs", False)
    assert h.registry.get("obs_scene") is None
    await h.manager.set_enabled("alguien.obs", True)
    assert h.registry.get("obs_scene") is not None


async def test_without_accepting_nothing_loads(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    await h.manager.install(package(tmp_path))
    assert h.registry.get("obs_scene") is None
    (status,) = h.manager.status()
    assert status.pending_permissions == ("net:localhost:4455",) and not status.active
    await h.manager.accept_permissions("alguien.obs")
    assert h.registry.get("obs_scene") is not None


async def test_never_during_a_game(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.playing = True
    await h.manager.install(package(tmp_path), accept=True)
    assert h.applied == [] and h.registry.get("obs_scene") is None  # el prefijo no cambia
    h.playing = False
    await h.manager.game_ended()
    assert h.registry.get("obs_scene") is not None and len(h.applied) == 1


async def test_a_broken_extension_does_not_sink_nyx(tmp_path: Path) -> None:
    def broken(ext: Installed) -> list[Tool[Any]]:
        raise RuntimeError("no arranca")

    h = Harness(tmp_path, factory=broken)
    await h.manager.install(package(tmp_path), accept=True)
    assert h.registry.get("obs_scene") is None
    assert any("no arranca" in p for p in h.manager.problems["alguien.obs"])
    assert app_catalog.profile_for("obs64.exe") is not None  # lo sin código, sí


async def test_a_tool_cannot_take_the_name_of_another(tmp_path: Path) -> None:
    h = Harness(tmp_path, factory=lambda ext: [fake_tool("delete_files")])
    before = h.registry.get("delete_files")
    await h.manager.install(package(tmp_path), accept=True)
    assert h.registry.get("delete_files") is before
    assert any("otra" in p for p in h.manager.problems["alguien.obs"])


async def test_group_names_do_not_clash_with_nyx(tmp_path: Path) -> None:
    groups = [{"name": "musica", "about": "OBS", "keywords": ["obs.*"], "tools": ["obs_scene"]}]
    h = Harness(tmp_path)
    await h.manager.install(package(tmp_path, groups=groups), accept=True)
    (group,) = h.manager.groups
    assert group.name == "alguien.obs.musica"
    assert group.keywords == ("obs",)  # normalizada y literal: nunca una regex de fuera


def test_registry_owners() -> None:
    registry = ToolRegistry()
    registry.register(fake_tool("a_tool"), owner="x.y")
    version = registry.version
    assert registry.unregister_owner("x.y") == ["a_tool"]
    assert registry.version > version and registry.get("a_tool") is None
