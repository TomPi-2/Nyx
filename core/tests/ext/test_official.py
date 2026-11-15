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
