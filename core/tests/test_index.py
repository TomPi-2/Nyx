import json
from pathlib import Path

import pytest

from nyx.index.aliases import generate, normalize
from nyx.index.db import IndexDB
from nyx.index.model import Kind
from nyx.index.scanners import ScanResult, folders, games
from nyx.index.scanners.tables import SETTINGS_PAGES, WEBSITES
from nyx.index.service import SystemIndex
from tests.conftest import sample_entries

# --- alias ---


def test_normalize() -> None:
    assert normalize("  Rocket League®  ") == "rocket league"
    assert normalize("Configuración del Ratón!") == "configuracion del raton"


def test_generate_aliases() -> None:
    assert generate("Visual Studio Code")[:1] == ("visual studio code",)
    assert {"vscode", "code", "vsc"} <= set(generate("Visual Studio Code"))
    assert "discord" in generate("Discord PTB")  # sin la etiqueta de versión
    assert "lol" in generate("League of Legends")
    assert generate("Fondos", ("Fondos de Imágenes",)) == ("fondos", "fondos de imagenes")


# --- escáneres ---


def test_parse_vdf() -> None:
    text = '"AppState"\n{\n\t"appid"\t\t"228980"\n\t"name"\t\t"Juego \\"X\\""\n\t"x" { "y" "1" }\n}'
    data = games.parse_vdf(text)
    assert data["AppState"]["appid"] == "228980"
    assert data["AppState"]["x"] == {"y": "1"}


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_scan_steam(tmp_path: Path) -> None:
    lib2 = tmp_path / "lib2"
    _write(
        tmp_path / "steamapps" / "libraryfolders.vdf",
        f'"libraryfolders" {{ "0" {{ "path" "{tmp_path}" }} "1" {{ "path" "{lib2}" }} }}'.replace(
            "\\", "\\\\"
        ),
    )
    _write(tmp_path / "steamapps" / "appmanifest_1.acf", '"AppState" { "appid" "1" "name" "PEAK" }')
    _write(
        tmp_path / "steamapps" / "appmanifest_2.acf",
        '"AppState" { "appid" "2" "name" "Steamworks Common Redistributables" }',
    )
    _write(lib2 / "steamapps" / "appmanifest_3.acf", '"AppState" { "appid" "3" "name" "Among Us" }')
    found = {e.name: e for e in games.scan_steam(tmp_path)}
    assert set(found) == {"PEAK", "Among Us"}
    assert found["PEAK"].launch.value == "steam://rungameid/1"


def test_scan_riot(tmp_path: Path) -> None:
    riot = tmp_path / "Riot Games"
    _write(
        riot / "RiotClientInstalls.json",
        json.dumps({"rc_default": "C:/Riot/RiotClientServices.exe"}),
    )
    (riot / "Metadata" / "valorant.live").mkdir(parents=True)
    found = {e.name: e for e in games.scan_riot(tmp_path)}
    assert set(found) == {"VALORANT"}
    launch = found["VALORANT"].launch
    assert launch.args == ("--launch-product=valorant", "--launch-patchline=live")
    assert found["VALORANT"].process == "valorant-win64-shipping.exe"


def test_scan_epic_skips_addons(tmp_path: Path) -> None:
    manifests = tmp_path / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    base = {"CatalogNamespace": "ns", "CatalogItemId": "id", "AppCategories": ["games"]}
    _write(
        manifests / "a.item", json.dumps({**base, "DisplayName": "Fortnite", "AppName": "Fortnite"})
    )
    _write(
        manifests / "b.item",
        json.dumps(
            {
                **base,
                "DisplayName": "Contenido de Fortnite",
                "AppName": "x",
                "MainGameAppName": "Fortnite",
            }
        ),
    )
    found = list(games.scan_epic(tmp_path))
    assert [e.name for e in found] == ["Fortnite"]
    assert found[0].launch.value.startswith("com.epicgames.launcher://apps/ns:id:Fortnite")


def test_scan_folders(tmp_path: Path) -> None:
    (tmp_path / "Imagenes" / "Fondos").mkdir(parents=True)
    (tmp_path / "Imagenes" / ".oculta").mkdir()
    entries = folders.scan({"Imágenes": tmp_path / "Imagenes"})
    names = {e.name for e in entries}
    assert names == {"Imágenes", "Fondos"}
    fondos = next(e for e in entries if e.name == "Fondos")
    assert "fondos de imagenes" in fondos.aliases


def test_tables_are_safe() -> None:
    assert all(uri.startswith("ms-settings:") for uri, _, _ in SETTINGS_PAGES)
    assert all(url.startswith("https://") for url, _, _ in WEBSITES)


# --- servicio ---


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("vscode", "Visual Studio Code"),
        ("el vscode", "Visual Studio Code"),
        ("spotify", "Spotify"),
        ("espotify", "Spotify"),
        ("el lol", "League of Legends"),
        ("valorant", "VALORANT"),
        ("discord", "Discord PTB"),
        ("descargas", "Descargas"),
        ("youtube", "YouTube"),
        ("raton", "Ratón"),
        ("configuracion", "Configuración"),
        ("rocket league", "Rocket League®"),
        ("visual studio", "Visual Studio 2022"),  # su nombre sin el año
        ("code", "Visual Studio Code"),  # dentro de un nombre más largo
    ],
)
async def test_resolve_confident(index: SystemIndex, query: str, expected: str) -> None:
    best = index.confident(index.resolve(query))
    assert best is not None and best.entry.name == expected


async def test_dedupe_prefers_game_and_settings_page(index: SystemIndex) -> None:
    valorant = [e for e in index.entries() if e.name == "VALORANT"]
    assert [e.kind for e in valorant] == [Kind.GAME]
    config = [e for e in index.entries() if e.name == "Configuración"]
    assert [e.kind for e in config] == [Kind.SETTING]


async def test_unknown_or_ambiguous_is_not_confident(index: SystemIndex) -> None:
    assert index.confident(index.resolve("photoshop")) is None
    assert index.confident(index.resolve("impresora 3d de marte")) is None
    assert index.confident(index.resolve("la web de mi primo")) is None
    assert index.resolve("") == []


async def test_short_aliases_only_match_exactly(index: SystemIndex) -> None:
    assert all(m.alias != "vsc" for m in index.resolve("visual"))


async def test_kinds_filter(index: SystemIndex) -> None:
    matches = index.resolve("documentos", {Kind.APP})
    assert all(m.entry.kind is Kind.APP for m in matches)


async def test_usage_and_user_aliases_survive_rescan(index: SystemIndex, tmp_path: Path) -> None:
    key = index.confident(index.resolve("spotify")).entry.key  # type: ignore[union-attr]
    index.record_use(key)
    index.add_user_alias("la musica", key)
    await index.refresh()
    best = index.confident(index.resolve("la musica"))
    assert best is not None and best.entry.key == key
    assert index.resolve("spotify")[0].score > 100  # desempate por uso


async def test_load_from_disk_without_scanning(tmp_path: Path) -> None:
    for sub in ("Descargas", "Documentos", "Imagenes/Fondos"):
        (tmp_path / sub).mkdir(parents=True)
    first = SystemIndex(IndexDB(tmp_path / "i.db"), scanner=lambda: sample_entries(tmp_path))
    await first.refresh()
    first.close()
    second = SystemIndex(IndexDB(tmp_path / "i.db"), scanner=lambda: [])
    second.load()
    assert len(second) == len(first)
    assert not second.needs_scan()
    second.close()


async def test_failed_source_keeps_previous_entries(tmp_path: Path) -> None:
    """Si un escáner falla (p. ej. COM sin inicializar), no se pierden sus entradas."""
    for sub in ("Descargas", "Documentos", "Imagenes/Fondos"):
        (tmp_path / sub).mkdir(parents=True)
    index = SystemIndex(IndexDB(tmp_path / "i.db"), scanner=lambda: sample_entries(tmp_path))
    await index.refresh()
    before = len(index)
    assert before
    tests = sum(1 for e in index.entries() if e.source == "test")
    others = [e for e in index.entries() if e.source != "test"]
    index._scanner = lambda: ScanResult(others, failed={"test"})
    await index.refresh()
    assert len(index) == before and tests
    index._scanner = lambda: ScanResult([])  # sin fallo: lo que no aparece, se va
    await index.refresh()
    assert len(index) == 0
    index.close()
