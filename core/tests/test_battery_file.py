"""La batería de frases (tests/battery/frases.jsonl) es la vara de medir del cerebro (6.17).

Sin modelo: cada frase nombra herramientas que existen y parámetros que tienen, para que un
error al escribirla no pase por un fallo del modelo (ni por un acierto). La 6.20b la usará
para comprobar que el grupo elegido contiene la herramienta esperada.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nyx.tools.registry import default_registry

PHRASES = Path(__file__).parent / "battery" / "frases.jsonl"
KINDS = {"respuesta", "no_sabe"}


def cases() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in PHRASES.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_every_phrase_names_real_tools_and_parameters() -> None:
    registry = default_registry()
    problems: list[str] = []
    for case in cases():
        frase = case["frase"]
        kinds = [k for k in ("tool", "plan", "tipo") if k in case]
        if len(kinds) != 1:
            problems.append(f"{frase}: debe tener una sola de tool, plan o tipo")
            continue
        if "tipo" in case:
            if case["tipo"] not in KINDS:
                problems.append(f"{frase}: tipo desconocido {case['tipo']!r}")
            continue
        steps = case["plan"] if "plan" in case else [case["tool"]]
        for step in steps:
            for name in step.split("|"):
                if registry.get(name) is None:
                    problems.append(f"{frase}: no existe la herramienta {name}")
        if "args" in case:
            options = [registry.get(n) for n in case["tool"].split("|")]
            for arg in case["args"]:
                if not any(t is not None and arg in t.params_model.model_fields for t in options):
                    problems.append(f"{frase}: {case['tool']} no tiene el parámetro {arg}")
    assert problems == []


def test_battery_is_large_and_has_no_repeats() -> None:
    all_cases = cases()
    frases = [c["frase"].casefold() for c in all_cases]
    assert len(frases) >= 300
    assert len(frases) == len(set(frases))
