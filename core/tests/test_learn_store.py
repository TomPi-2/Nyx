"""Peticiones corregidas guardadas para entrenar (plan «Cerebro 2», C0)."""

from __future__ import annotations

import json
import wave
from pathlib import Path

import numpy as np
import pytest

from nyx.learn.store import CorrectionStore, Kind, correction_kind
from tests.test_pipeline import Harness


@pytest.mark.parametrize(
    ("raw", "kind"),
    [
        ("Deshazlo.", Kind.UNDO),
        ("No, deshazlo", Kind.UNDO),
        ("Recupéralo", Kind.UNDO),
        ("No, el otro.", Kind.CORRECTION),
        ("No, el Spotify.", Kind.CORRECTION),
        ("No, a las siete y media", Kind.CORRECTION),
        ("Eso no es lo que te he pedido", Kind.CORRECTION),
        ("Te has equivocado", Kind.CORRECTION),
        ("Eso no era para ti", Kind.NOT_FOR_ME),
        ("No te he llamado", Kind.NOT_FOR_ME),
        ("No me ha hecho nada", None),  # empieza por «no», pero no corrige
        ("Abre Spotify", None),
        ("¿No tienes frío?", None),
        ("", None),
    ],
)
def test_correction_kind(raw: str, kind: Kind | None) -> None:
    assert correction_kind(raw) == kind


def make(tmp_path: Path, *, enabled: bool = True) -> tuple[CorrectionStore, list[float]]:
    now = [100.0]
    actions = {"r1": [{"tool": "save_note", "params": {"title": "x"}, "ok": True, "extra": 1}]}
    store = CorrectionStore(
        tmp_path,
        enabled=enabled,
        actions=lambda rid: actions.get(rid, []),
        clock=lambda: now[0],
    )
    return store, now


def test_saves_the_previous_request_when_corrected(tmp_path: Path) -> None:
    store, _ = make(tmp_path)
    audio = np.arange(1600, dtype=np.int16)
    store.begin("r1", "Nix, apunta el blog de notas, pizza caprese.", "Apunta…", audio)
    assert store.check("Nix, apunta el blog de notas, pizza caprese.") is None
    store.begin("r2", "Deshazlo.", "Deshazlo.")
    assert store.check("Deshazlo.", reply="He guardado la nota.") is Kind.UNDO
    lines = (tmp_path / "correcciones.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["tipo"] == "deshacer"
    assert entry["oido"].startswith("Nix, apunta el blog")
    assert entry["hizo"] == [
        {
            "tool": "save_note",
            "params": {"title": "x"},
            "decision": None,
            "ok": True,
            "message": None,
        }
    ]
    assert entry["dijo"] == "He guardado la nota."
    with wave.open(str(tmp_path / f"{entry['id']}.wav")) as w:
        assert w.getframerate() == 16_000
        assert w.getnframes() == 1600


def test_only_once_and_only_recent(tmp_path: Path) -> None:
    store, now = make(tmp_path)
    store.begin("r1", "Abre Discord.", "Abre Discord.")
    store.begin("r2", "No, el otro.", "No, el otro.")
    store.check("No, el otro.")
    store.begin("r3", "Deshazlo.", "Deshazlo.")
    store.check("Deshazlo.")  # corrige «No, el otro.» (r2), no otra vez r1
    entries = (tmp_path / "correcciones.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(e)["oido"] for e in entries] == ["Abre Discord.", "No, el otro."]
    store.begin("r4", "Abre Steam.", "Abre Steam.")
    now[0] += 500  # mucho después: ya no se refiere a eso
    store.begin("r5", "Deshazlo.", "Deshazlo.")
    store.check("Deshazlo.")
    assert len((tmp_path / "correcciones.jsonl").read_text(encoding="utf-8").splitlines()) == 2


def test_disabled_saves_nothing(tmp_path: Path) -> None:
    store, _ = make(tmp_path, enabled=False)
    store.begin("r1", "Abre Discord.", "Abre Discord.")
    store.begin("r2", "Deshazlo.", "Deshazlo.")
    assert store.check("Deshazlo.") is None
    assert not any(tmp_path.iterdir())


def wavs(folder: Path) -> int:
    return len(list(folder.glob("*.wav")))


def read_entry(folder: Path) -> dict[str, str]:
    data: dict[str, str] = json.loads((folder / "correcciones.jsonl").read_text(encoding="utf-8"))
    return data


async def test_pipeline_saves_a_corrected_voice_request(tmp_path: Path) -> None:
    h = Harness()
    h.p.corrections = CorrectionStore(tmp_path, enabled=True)
    h.stt.script = ["Nix, ¿cómo se dice hola en alemán?"]
    await h.say()
    await h.p.wait_idle()
    h.stt.script = ["Nix, te has equivocado."]
    await h.say()
    await h.p.wait_idle()
    entry = read_entry(tmp_path)
    assert entry["oido"] == "Nix, ¿cómo se dice hola en alemán?"
    assert entry["correccion"] == "Te has equivocado."
    assert entry["dijo"].endswith("En alemán se dice Hallo.")
    assert wavs(tmp_path) == 1  # con el audio de la petición corregida
    await h.p.close()
