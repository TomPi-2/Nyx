"""Router, paso 2 de Cerebro 2: los fallos que encontró el arnés de audio (2026-11-23)."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from nyx.brain.router import Miss, Route, route
from nyx.index.db import IndexDB
from nyx.index.service import SystemIndex
from tests.conftest import app, sample_entries


@pytest.fixture
async def idx(tmp_path: Path) -> AsyncIterator[SystemIndex]:
    for sub in ("Descargas", "Documentos", "Imagenes/Fondos"):
        (tmp_path / sub).mkdir(parents=True)
    extra = [
        app("Opera GX", "Opera GX Stable", "opera.exe"),
        app("Battle.net", "Battle.net", "battle.net.exe"),
        app("Epic Games Launcher", "EpicGames", "epicgameslauncher.exe"),
    ]
    index = SystemIndex(
        IndexDB(tmp_path / "i.db"), scanner=lambda: sample_entries(tmp_path) + extra
    )
    await index.refresh()
    yield index
    index.close()


def calls(text: str, index: SystemIndex) -> list[tuple[str, dict[str, object]]]:
    result = route(text, index)
    assert isinstance(result, Route), f"{text!r} → {result!r}"
    return [(c.name, c.arguments) for c in result.calls]


async def test_close_several_apps(idx: SystemIndex) -> None:
    assert calls("cierra el Opera y el Spotify y apaga el ordenador", idx) == [
        ("close_app", {"name": "opera"}),
        ("close_app", {"name": "spotify"}),
        ("system_power", {"action": "shutdown"}),
    ]


@pytest.mark.parametrize(
    "text",
    [
        "cierra todo",
        "cierra todas las aplicaciones",
        "ciérrame todos los programas",
        "cierra todas",
    ],
)
async def test_close_everything(text: str, idx: SystemIndex) -> None:
    assert calls(text, idx) == [("close_all_apps", {})]


async def test_close_everything_then_shut_down(idx: SystemIndex) -> None:
    assert calls("cierra todo y apaga el ordenador", idx) == [
        ("close_all_apps", {}),
        ("system_power", {"action": "shutdown"}),
    ]


async def test_one_app_is_one_close(idx: SystemIndex) -> None:
    assert calls("cierra el bloc de notas", idx) == [("close_app", {"name": "bloc de notas"})]


@pytest.mark.parametrize("text", ["abre Battle.net", "abre battle punto net"])
async def test_installed_app_beats_the_website(text: str, idx: SystemIndex) -> None:
    assert calls(text, idx) == [("open_app", {"name": "Battle.net"})]


async def test_a_real_website_is_still_a_website(idx: SystemIndex) -> None:
    assert calls("abre marca.com", idx) == [("open_url", {"target": "marca punto com"})]


@pytest.mark.parametrize(
    ("text", "written"),
    [
        ("apunta en el bloc de notas la lista de la compra", "la lista de la compra"),
        ("apunta el blog de notas, pizza caprese", "pizza caprese"),
        ("anótame en el bloc de notas que llame a Marta", "llame a Marta"),
    ],
)
async def test_note_in_notepad_opens_it_and_writes(
    text: str, written: str, idx: SystemIndex
) -> None:
    assert calls(text, idx) == [
        ("open_app", {"name": "Bloc de notas"}),
        ("wait_for_window", {"name": "Bloc de notas"}),
        ("type_text", {"app": "Bloc de notas", "text": written}),
    ]


async def test_a_nyx_note_is_still_a_nyx_note(idx: SystemIndex) -> None:
    assert calls("apunta en una nota que mañana tengo dentista", idx)[0][0] == "save_note"


@pytest.mark.parametrize(
    ("text", "name"),
    [("abre espotifai", "Spotify"), ("abre balorant", "VALORANT"), ("abre roket ligue", None)],
)
async def test_opens_what_sounds_the_same(text: str, name: str | None, idx: SystemIndex) -> None:
    opened = calls(text, idx)[0]
    assert opened[0] == "open_app"
    assert name is None or opened[1] == {"name": name}


@pytest.mark.parametrize("text", ["abre epic gueims", "abre Applelepic Games"])
async def test_offers_what_sounds_almost_the_same(text: str, idx: SystemIndex) -> None:
    result = route(text, idx)
    assert isinstance(result, Miss) and result.offer is not None
    assert result.offer_name == "Epic Games Launcher"
    assert [c.name for c in result.offer.calls] == ["open_app"]


async def test_nothing_offered_when_nothing_sounds_alike(idx: SystemIndex) -> None:
    result = route("abre la tele", idx)
    assert isinstance(result, Miss) and result.offer is None
