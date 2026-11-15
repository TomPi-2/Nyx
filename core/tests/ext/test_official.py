"""7.14: las extensiones oficiales que vienen con Nyx (empaquetar y encontrarlas)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from nyx.ext import official
from nyx.ext.store import PackageError, read_package


def test_the_repository_ones_pack_and_validate(tmp_path: Path) -> None:
    found = official.packages(cache=tmp_path)
    ids = sorted(read_package(p)[0].id for p in found)
    assert ids == ["tepnyx.obs", "tepnyx.spotify"]
    for path in found:
        names = zipfile.ZipFile(path).namelist()
        assert not any(n.startswith("tests/") for n in names)
    # Sin cambios en el código, no se vuelven a empaquetar.
    stamps = [p.stat().st_mtime_ns for p in found]
    assert [p.stat().st_mtime_ns for p in official.packages(cache=tmp_path)] == stamps


def test_installed_nyx_uses_the_signed_ones(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = tmp_path / "core" / "app"
    app.mkdir(parents=True)
    (tmp_path / "core" / "extensiones").mkdir()
    (tmp_path / "core" / "extensiones" / "tepnyx.obs.nyxext").write_bytes(b"x")
    monkeypatch.setattr(official, "_code_root", lambda: app)
    assert [p.name for p in official.packages()] == ["tepnyx.obs.nyxext"]


def test_a_broken_folder_is_not_packed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    trashed: list[Path] = []
    monkeypatch.setattr(official, "_trash", trashed.append)  # nada a la papelera de verdad
    folder = tmp_path / "mala"
    folder.mkdir()
    (folder / "manifest.json").write_text("{}", encoding="utf-8")
    with pytest.raises(PackageError):
        official.pack_folder(folder, tmp_path / "mala.nyxext")
    assert not (tmp_path / "mala.nyxext").exists()
    assert trashed == [tmp_path / "mala.nyxext.tmp"]


# --- Para cerrar la 0.7: las oficiales en un Nyx de verdad, sin reiniciar ----------------------


async def test_official_ones_install_work_update_and_uninstall(tmp_path: Path) -> None:
    """Gestor, herramientas y host de verdad (sin encerrar, para ir rápido): instalar, usar,
    actualizar y desinstalar sin reiniciar Nyx, y una herramienta que falla no la tumba."""
    import json

    from nyx.bus import EventBus
    from nyx.ext.api import ExtensionApi
    from nyx.ext.host import ExtensionHost
    from nyx.ext.manager import ExtensionManager
    from nyx.ext.store import ExtensionStore
    from nyx.ext.tools import make_tools
    from nyx.tools.registry import default_registry
    from tests.test_ext_host import PlainLauncher

    packs = {read_package(p)[0].id: p for p in official.packages(cache=tmp_path / "cache")}
    store = ExtensionStore(tmp_path / "ext", tmp_path / "s.json", trash=lambda p: None)
    api = ExtensionApi(
        EventBus(),
        lambda _id: (
            tuple(store.get(_id).manifest.permissions)  # type: ignore[union-attr]
            if store.get(_id)
            else ()
        ),
        settings_of=lambda _id: ("client_id",),
        setting_reader=lambda _id, _key: None,  # Spotify sin conectar
    )
    host = ExtensionHost(PlainLauncher(tmp_path / "datos"), handlers=api.handlers)
    registry = default_registry()

    async def apply(_selector: object) -> None:
        return None

    manager = ExtensionManager(
        store,
        registry,
        budget_chars=27033,
        apply_selector=apply,
        tool_factory=lambda ext: make_tools(ext, host),
    )
    try:
        for ext_id in ("tepnyx.obs", "tepnyx.spotify"):
            await manager.install(packs[ext_id], accept=True, dev=True)
        assert registry.get("obs_record") is not None and registry.get("spotify_play") is not None
        assert manager.problems == {} or all(not v for v in manager.problems.values())

        # Usarla: sin conectar, Spotify lo explica (sin red ni nada de fuera).
        tool = registry.get("spotify_now")
        assert tool is not None
        result = await tool.run(tool.params_model(), None)  # type: ignore[arg-type]
        assert not result.ok and "cómo conecto Spotify" in (result.secondary or "")
        assert host.crashes.get("tepnyx.spotify") is None  # un fallo suyo no es una caída

        # Actualizar: misma extensión, versión nueva, sin reiniciar.
        folder = official.source_dir() / "tepnyx.spotify"  # type: ignore[operator]
        copy = tmp_path / "spotify-1.0.1"
        import shutil

        shutil.copytree(folder, copy)
        data = json.loads((copy / "manifest.json").read_text(encoding="utf-8"))
        data["version"] = "1.0.1"
        (copy / "manifest.json").write_text(json.dumps(data), encoding="utf-8")
        result_update = await manager.install(
            official.pack_folder(copy, tmp_path / "v2.nyxext"), dev=True
        )
        assert result_update.status == "updated"
        assert store.get("tepnyx.spotify").manifest.version == "1.0.1"  # type: ignore[union-attr]
        assert registry.get("spotify_play") is not None

        # Desinstalar: sus herramientas se van; las de Nyx siguen.
        await manager.uninstall("tepnyx.obs")
        await manager.uninstall("tepnyx.spotify")
        assert registry.get("obs_record") is None and registry.get("spotify_play") is None
        assert registry.get("open_app") is not None
    finally:
        await host.stop_all()
