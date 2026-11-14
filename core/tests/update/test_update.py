"""9.05: copia de seguridad, migraciones versionadas (y restaurar si fallan) y buen momento."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from nyx.update import backup as backup_mod
from nyx.update.backup import DataFiles, make_backup, prune, restore
from nyx.update.migrations import Migration, last_version, migrate, parse_version
from nyx.update.moment import UpdateGate


@pytest.fixture
def files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DataFiles:
    f = DataFiles(tmp_path / "roaming", tmp_path / "local")
    f.roaming.mkdir()
    f.local.mkdir()
    (f.roaming / "settings.json").write_text('{"version": 1}', encoding="utf-8")
    (f.roaming / "extensions.json").write_text('{"extensions": {}}', encoding="utf-8")
    with sqlite3.connect(f.local / "alarms.db") as db:
        db.execute("CREATE TABLE a (x)")
        db.execute("INSERT INTO a VALUES (1)")
    sent: list[Path] = []

    def trash(path: Path) -> None:
        sent.append(path)
        import shutil

        shutil.rmtree(path) if path.is_dir() else path.unlink()

    monkeypatch.setattr(backup_mod, "_trash", trash)
    return f


def test_versions_compare_as_numbers() -> None:
    assert parse_version("v1.10.0") > parse_version("1.9.0")
    assert parse_version("1.142.245") == (1, 142, 245)
    with pytest.raises(ValueError):
        parse_version("1.2")


def test_backup_and_restore(files: DataFiles) -> None:
    folder = make_backup("1.0.0", files)
    (files.roaming / "settings.json").write_text("roto", encoding="utf-8")
    with sqlite3.connect(files.local / "alarms.db") as db:
        db.execute("DELETE FROM a")
    restore(folder)
    assert json.loads((files.roaming / "settings.json").read_text(encoding="utf-8")) == {
        "version": 1
    }
    with sqlite3.connect(files.local / "alarms.db") as db:
        assert db.execute("SELECT count(*) FROM a").fetchone() == (1,)


def test_only_three_backups_are_kept(files: DataFiles) -> None:
    start = datetime(2026, 11, 14)
    for i in range(5):
        make_backup(f"1.0.{i}", files, now=start + timedelta(minutes=i))
    prune(files)
    left = sorted(p.name for p in files.backups.iterdir())
    assert len(left) == 3 and left[-1].endswith("1.0.4")


def test_first_run_just_remembers(files: DataFiles) -> None:
    assert migrate("1.0.0", files).applied == ()
    assert last_version(files) == "1.0.0"


def test_says_where_it_was_updated_from(files: DataFiles) -> None:
    """9.06: «Actualizada a la 1.1.0» al arrancar la versión nueva (y solo entonces)."""
    assert migrate("1.0.0", files, []).updated_from is None
    assert migrate("1.1.0", files, []).updated_from == "1.0.0"
    assert migrate("1.1.0", files, []).updated_from is None


def test_migrations_in_order_and_only_the_new_ones(files: DataFiles) -> None:
    done: list[str] = []
    migrations = [
        Migration("1.2.0", "b", lambda f: done.append("b")),
        Migration("1.1.0", "a", lambda f: done.append("a")),
        Migration("1.0.0", "vieja", lambda f: done.append("vieja")),
        Migration("2.0.0", "futura", lambda f: done.append("futura")),
    ]
    migrate("1.0.0", files, migrations)
    outcome = migrate("1.2.0", files, migrations)
    assert done == ["a", "b"] and outcome.applied == ("a", "b")
    assert last_version(files) == "1.2.0"
    assert any(files.backups.iterdir())  # hubo copia antes


def test_a_failed_migration_restores_the_copy(files: DataFiles) -> None:
    def breaks(f: DataFiles) -> None:
        (f.roaming / "settings.json").write_text("a medias", encoding="utf-8")
        raise RuntimeError("se fue la luz")

    migrate("1.0.0", files, [])
    outcome = migrate("1.1.0", files, [Migration("1.1.0", "rompe", breaks)])
    assert outcome.restored and "se fue la luz" in outcome.error
    assert (files.roaming / "settings.json").read_text(encoding="utf-8") == '{"version": 1}'
    assert last_version(files) == "1.0.0"  # se volverá a intentar


def test_going_back_does_not_migrate(files: DataFiles) -> None:
    ran: list[str] = []
    migrate("1.2.0", files, [])
    migrate("1.1.0", files, [Migration("1.1.0", "x", lambda f: ran.append("x"))])
    assert ran == [] and last_version(files) == "1.1.0"


def test_update_gate() -> None:
    state = {"busy": None}
    gate = UpdateGate()
    gate.add("pipeline", lambda: state["busy"])
    gate.add("roto", lambda: 1 / 0)  # si no se sabe, mejor esperar
    assert not gate.ready() and gate.blocked_by() == ["roto: no se sabe"]
    gate.checks.pop("roto")
    assert gate.ready()
    state["busy"] = "Nyx está atendiendo una petición"
    assert gate.blocked_by() == ["Nyx está atendiendo una petición"]
