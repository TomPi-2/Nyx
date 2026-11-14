"""7.02: instalar, actualizar, desactivar y desinstalar extensiones sin que un paquete malo
(rutas que salen, enlaces, zip bomba, fallo a medias) deje a Nyx mal."""

from __future__ import annotations

import json
import stat
import zipfile
from pathlib import Path
from typing import Any

import pytest

from nyx.ext import store as store_mod
from nyx.ext.store import ExtensionStore, PackageError, read_package

BASE: dict[str, Any] = {
    "id": "tepnyx.prueba",
    "name": "Prueba",
    "version": "1.0.0",
    "author": "Tepnyx",
    "nyx_api": ">=1.0 <2.0",
    "kinds": ["tools"],
    "permissions": ["notify"],
}


def package(
    tmp: Path,
    name: str = "p.nyxext",
    *,
    manifest: dict[str, Any] | None = None,
    files: dict[str, bytes] | None = None,
    **changes: Any,
) -> Path:
    data = {**(manifest or BASE), **changes}
    path = tmp / name
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(data))
        for member, blob in (files or {"README.md": b"hola"}).items():
            zf.writestr(member, blob)
    return path


class Trash:
    def __init__(self) -> None:
        self.sent: list[Path] = []

    def __call__(self, path: Path) -> None:
        self.sent.append(path)
        import shutil

        shutil.rmtree(path) if path.is_dir() else path.unlink()


@pytest.fixture
def trash() -> Trash:
    return Trash()


@pytest.fixture
def store(tmp_path: Path, trash: Trash) -> ExtensionStore:
    return ExtensionStore(tmp_path / "ext", tmp_path / "extensions.json", trash=trash)


def test_install_accept_and_reload(tmp_path: Path, store: ExtensionStore) -> None:
    result = store.install(package(tmp_path), accept=True)
    assert result.status == "installed"
    found = store.get("tepnyx.prueba")
    assert found is not None and found.active
    assert (found.path / "README.md").read_bytes() == b"hola"
    # El estado sobrevive a reiniciar Nyx.
    again = ExtensionStore(store.root, store.state_path)
    assert [e.id for e in again.active()] == ["tepnyx.prueba"]


def test_without_accepting_it_stays_off(tmp_path: Path, store: ExtensionStore) -> None:
    result = store.install(package(tmp_path))
    assert result.status == "needs_permissions" and result.new_permissions == ("notify",)
    assert store.active() == []
    store.accept_permissions("tepnyx.prueba")
    assert [e.id for e in store.active()] == ["tepnyx.prueba"]


def test_an_update_asking_for_more_waits(
    tmp_path: Path, store: ExtensionStore, trash: Trash
) -> None:
    store.install(package(tmp_path), accept=True)
    more = package(tmp_path, "v2.nyxext", version="1.1.0", permissions=["notify", "secrets"])
    result = store.install(more)
    assert result.status == "needs_permissions" and result.new_permissions == ("secrets",)
    # Sigue la anterior, activa y con lo que ya tenía.
    found = store.get("tepnyx.prueba")
    assert found is not None and found.manifest.version == "1.0.0" and found.active
    store.accept_permissions("tepnyx.prueba")
    found = store.get("tepnyx.prueba")
    assert found is not None and found.manifest.version == "1.1.0" and found.active
    assert store.root / "tepnyx.prueba" / "1.0.0" in trash.sent  # la vieja, a la papelera


def test_an_update_with_the_same_permissions_switches(
    tmp_path: Path, store: ExtensionStore
) -> None:
    store.install(package(tmp_path), accept=True)
    result = store.install(package(tmp_path, "v2.nyxext", version="2.0.0"))
    assert result.status == "updated"
    found = store.get("tepnyx.prueba")
    assert found is not None and found.manifest.version == "2.0.0"


def test_no_downgrades(tmp_path: Path, store: ExtensionStore) -> None:
    store.install(package(tmp_path, version="2.0.0"), accept=True)
    with pytest.raises(PackageError, match="más nueva"):
        store.install(package(tmp_path, "old.nyxext", version="1.9.9"))


def test_a_failure_halfway_keeps_the_old_one(
    tmp_path: Path, store: ExtensionStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    store.install(package(tmp_path), accept=True)

    def broken(pkg: Path, members: Any, to: Path) -> None:
        (to / "a medias.txt").write_text("x")
        raise OSError("se fue la luz")

    monkeypatch.setattr(store_mod, "_extract", broken)
    with pytest.raises(OSError):
        store.install(package(tmp_path, "v2.nyxext", version="1.1.0"))
    found = store.get("tepnyx.prueba")
    assert found is not None and found.manifest.version == "1.0.0" and found.active
    leftovers = [p.name for p in (store.root / "tepnyx.prueba").iterdir()]
    assert leftovers == ["1.0.0"]  # sin carpetas a medias


def test_reinstalling_the_same_version(tmp_path: Path, store: ExtensionStore) -> None:
    store.install(package(tmp_path), accept=True)
    store.install(package(tmp_path, files={"README.md": b"nuevo"}), accept=True)
    found = store.get("tepnyx.prueba")
    assert found is not None and (found.path / "README.md").read_bytes() == b"nuevo"


def test_uninstall_goes_to_the_trash_and_can_come_back(
    tmp_path: Path, store: ExtensionStore, trash: Trash
) -> None:
    store.install(package(tmp_path), accept=True)
    store.uninstall("tepnyx.prueba")
    assert store.get("tepnyx.prueba") is None
    assert store.root / "tepnyx.prueba" in trash.sent
    store.install(package(tmp_path), accept=True)
    assert store.get("tepnyx.prueba") is not None


def test_disable(tmp_path: Path, store: ExtensionStore) -> None:
    store.install(package(tmp_path), accept=True)
    store.set_enabled("tepnyx.prueba", False)
    assert store.active() == [] and len(store.installed()) == 1


@pytest.mark.parametrize(
    "member",
    [
        "../fuera.txt",
        "tools/../../fuera.txt",
        "/absoluta.txt",
        "C:/Windows/x.txt",
        "con.txt",
        "tools/aux",
        "punto.",
        "datos.txt:oculto",
    ],
)
def test_paths_that_escape_or_trick_windows(
    tmp_path: Path, store: ExtensionStore, member: str
) -> None:
    with pytest.raises(PackageError):
        store.install(package(tmp_path, files={member: b"x"}))
    assert not (tmp_path / "fuera.txt").exists()
    assert store.installed() == []


def test_links_are_refused(tmp_path: Path, store: ExtensionStore) -> None:
    path = package(tmp_path)
    with zipfile.ZipFile(path, "a") as zf:
        info = zipfile.ZipInfo("enlace")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(info, "C:/Users")
    with pytest.raises(PackageError, match="enlace"):
        store.install(path)


def test_a_zip_bomb(tmp_path: Path, store: ExtensionStore) -> None:
    with pytest.raises(PackageError, match="zip bomba"):
        store.install(package(tmp_path, files={"ceros.bin": bytes(8 * 1024 * 1024)}))


def test_too_many_files(
    tmp_path: Path, store: ExtensionStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(store_mod, "MAX_FILES", 5)
    files = {f"f{i}.txt": b"x" for i in range(6)}
    with pytest.raises(PackageError, match="más de 5"):
        store.install(package(tmp_path, files=files))


def test_too_big(tmp_path: Path, store: ExtensionStore, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store_mod, "MAX_TOTAL_BYTES", 1000)
    with pytest.raises(PackageError, match="demasiado grande"):
        store.install(package(tmp_path, files={"a.bin": bytes(range(256)) * 8}))


def test_duplicates_ignoring_case(tmp_path: Path, store: ExtensionStore) -> None:
    with pytest.raises(PackageError, match="repetido"):
        store.install(package(tmp_path, files={"A.txt": b"1", "a.txt": b"2"}))


@pytest.mark.parametrize("blob", [b"no es un zip", b""])
def test_not_a_package(tmp_path: Path, blob: bytes) -> None:
    path = tmp_path / "x.nyxext"
    path.write_bytes(blob)
    with pytest.raises(PackageError):
        read_package(path)


def test_without_manifest(tmp_path: Path) -> None:
    path = tmp_path / "x.nyxext"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("README.md", "hola")
    with pytest.raises(PackageError, match=r"manifest.json"):
        read_package(path)


def test_a_bad_manifest_is_not_installed(tmp_path: Path, store: ExtensionStore) -> None:
    with pytest.raises(PackageError, match="manifiesto"):
        store.install(package(tmp_path, permissions=["keyboard:game"]))
    assert not (store.root / "tepnyx.prueba").exists() or not any(
        (store.root / "tepnyx.prueba").iterdir()
    )


def test_a_damaged_state_file(tmp_path: Path) -> None:
    state = tmp_path / "extensions.json"
    state.write_text("{roto", encoding="utf-8")
    store = ExtensionStore(tmp_path / "ext", state)
    assert store.installed() == []
    assert (tmp_path / "extensions.json.dañado").exists()
