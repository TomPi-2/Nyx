"""7.11 (núcleo): lo que pide Ajustes → Extensiones y lo que se le contesta."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from nyx.bus import EventBus
from nyx.events import ExtRequested, ExtStatusChanged
from nyx.ext.manager import ExtensionManager
from nyx.ext.service import ExtensionsService
from nyx.ext.store import ExtensionStore
from nyx.settings.model import Settings
from nyx.tools.registry import default_registry
from tests.ext.conftest import TRUSTED, signed


def package(tmp: Path, *, sign: bool) -> Path:
    path = tmp / "luces.nyxext"
    manifest = {
        "id": "tepnyx.luces",
        "name": "Luces",
        "version": "1.0.0",
        "author": "Tepnyx",
        "nyx_api": "1.0",
        "kinds": ["knowledge"],
    }
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("knowledge/a.md", "## Luces\n\nSe encienden.")
    return signed(path) if sign else path


class Harness:
    def __init__(self, tmp: Path, *, dev_mode: bool = False) -> None:
        self.bus = EventBus()
        self.settings = Settings()
        self.settings.extensions.dev_mode = dev_mode
        store = ExtensionStore(
            tmp / "ext", tmp / "s.json", trash=lambda p: None, trusted_keys=TRUSTED
        )

        async def apply(selector: Any) -> None:
            return None

        self.manager = ExtensionManager(
            store, default_registry(), budget_chars=27033, apply_selector=apply
        )
        self.service = ExtensionsService(self.bus, self.manager, self.settings)
        self.seen: list[ExtStatusChanged] = []

        async def on_status(e: ExtStatusChanged) -> None:
            self.seen.append(e)

        self.bus.subscribe(ExtStatusChanged, on_status)

    async def ask(self, action: Any, **kw: str) -> ExtStatusChanged:
        await self.bus.publish(ExtRequested(action, **kw))
        return self.seen[-1]


async def test_inspect_then_install(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    path = package(tmp_path, sign=True)
    shown = await h.ask("inspect", path=str(path))
    assert shown.inspect is not None and shown.inspect["signed"] and shown.inspect["installable"]
    assert shown.items == []  # inspeccionar no instala nada
    done = await h.ask("install", path=str(path))
    (item,) = done.items
    assert item["id"] == "tepnyx.luces" and item["active"] and not item["dev"]


async def test_unsigned_needs_developer_mode(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    path = package(tmp_path, sign=False)
    shown = await h.ask("inspect", path=str(path))
    assert shown.inspect is not None and not shown.inspect["installable"]
    refused = await h.ask("install", path=str(path))
    assert refused.error and "modo desarrollador" in refused.error and refused.items == []
    h.settings.extensions.dev_mode = True
    done = await h.ask("install", path=str(path))
    assert done.items[0]["dev"] is True  # «sin revisar»


async def test_enable_disable_uninstall(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    await h.ask("install", path=str(package(tmp_path, sign=True)))
    off = await h.ask("disable", ext_id="tepnyx.luces")
    assert off.items[0]["enabled"] is False
    gone = await h.ask("uninstall", ext_id="tepnyx.luces")
    assert gone.items == []


async def test_only_nyxext_files(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    other = tmp_path / "notas.txt"
    other.write_text("hola", encoding="utf-8")
    answer = await h.ask("inspect", path=str(other))
    assert answer.error and ".nyxext" in answer.error
