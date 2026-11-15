"""Batería de voz (2026-11-15): cada frase que resuelve el router, dicha como la transcribe
Whisper («Nix,» delante, repetida, con «oye», «eh…», «por favor» o un «Gracias.» inventado),
tiene que hacer lo mismo. Lo mismo que `scripts/voice_battery.py`, con el índice de pruebas."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from nyx.index.service import SystemIndex
from nyx.stt.normalize import normalize

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import voice_battery
from battery import judge

CASES = [
    json.loads(line)
    for line in voice_battery.FRASES.read_text(encoding="utf-8").splitlines()
    if line.strip()
]


@pytest.mark.parametrize("variant", sorted(voice_battery.VARIANTS))
def test_whisper_variants_do_the_same(index: SystemIndex, variant: str) -> None:
    make = voice_battery.VARIANTS[variant]
    checked, failed = 0, []
    for case in CASES:
        if "tipo" in case:
            continue
        calls, text, path = voice_battery.run(case["frase"], index)
        if path != "router" or not judge(case, calls, text)[0]:
            continue  # con el índice de pruebas no se resuelve: no es de esta batería
        checked += 1
        said = make(case["frase"])
        calls, text, path = voice_battery.run(said, index)
        ok, why = judge({**case, "frase": said}, calls, text)
        if path != "router" or not ok:
            failed.append(f"{said!r}: {path} {why}")
    assert checked > 100
    assert failed == []


@pytest.mark.parametrize(
    ("heard", "clean"),
    [
        ("Siguiente. Siguiente.", "Siguiente."),
        ("Más pequeño más pequeño", "Más pequeño"),
        ("Melocotón. Melocotón.", "Melocotón."),
        ("Nyx. Nyx. Pasa la canción.", "Pasa la canción."),
        ("Pasa la canción. Gracias.", "Pasa la canción."),
        ("Abre Spotify y abre Discord.", "Abre Spotify y abre Discord."),  # no es una repetición
        ("Gracias.", ""),
    ],
)
def test_normalize_whisper_habits(heard: str, clean: str) -> None:
    assert normalize(heard) == clean
