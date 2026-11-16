"""Batería de voz: lo mismo dicho como lo transcribe Whisper (2026-11-15).

Toma cada frase de `tests/battery/frases.jsonl` que el router ya resuelve bien y la
transforma como sale de verdad en los registros: «Nix,» o «Niks» delante, sin tildes ni
puntuación, repetida («Siguiente. Siguiente.»), con «a ver», «oye», «eh…», «por favor» o
un «Gracias.» inventado al final. Cada variante tiene que hacer lo mismo que la original. Sin
el modelo (solo el camino rápido): tarda unos segundos.

    uv run python scripts/voice_battery.py
    uv run python scripts/voice_battery.py --informe ../docs/benchmarks/voz-variantes.md
    uv run python scripts/voice_battery.py --exportar tests/battery/voz.jsonl
        (las variantes en el formato de battery.py, para pasarlas también con el modelo)
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from battery import judge

from nyx.brain.router import Route, refusal, route
from nyx.executor import ToolCall
from nyx.index.service import SystemIndex
from nyx.stt.normalize import normalize

FRASES = Path(__file__).resolve().parents[1] / "tests" / "battery" / "frases.jsonl"


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    # Sin tildes, en minúsculas y sin los signos de la frase; lo de dentro de una palabra
    # («marca.com», «10:50», «@») se queda, como lo escribe Whisper.
    return "".join(c for c in text if c not in "¿?¡!,;").lower().strip().rstrip(".")


def _bare(text: str) -> str:
    return text.strip().rstrip(".!?")


#: Nombre de la variante → cómo se transforma la frase (todas salen en los registros reales).
VARIANTS: dict[str, Callable[[str], str]] = {
    "nix_coma": lambda t: f"Nix, {t[0].lower()}{t[1:]}",
    "nyx_punto": lambda t: f"Nyx. {t}",
    "niks": lambda t: f"Niks, {t[0].lower()}{t[1:]}",
    "sin_tildes": _plain,
    "repetida": lambda t: f"{_bare(t)}. {_bare(t)}.",
    "a_ver": lambda t: f"A ver, {t[0].lower()}{t[1:]}",
    "oye": lambda t: f"Oye, {t[0].lower()}{t[1:]}",
    "eh": lambda t: f"Eh... {t[0].lower()}{t[1:]}",
    "por_favor": lambda t: f"{_bare(t)}, por favor.",
    "gracias_final": lambda t: f"{_bare(t)}. Gracias.",
    "nix_y_frase_doble": lambda t: f"Nix. Nix. {t}",
}


def run(text: str, index: SystemIndex) -> tuple[list[ToolCall] | None, str | None, str]:
    """(llamadas, texto, camino) como en Nyx tras transcribir: normalizar y router."""
    clean = normalize(text)
    if not clean:
        return None, None, "vacía"
    if (no := refusal(clean, index)) is not None:
        return None, no[0], "negativa"
    routed = route(clean, index)
    if isinstance(routed, Route):
        return routed.calls, None, "router"
    return None, None, "llm"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--informe", type=Path)
    parser.add_argument("--exportar", type=Path)
    args = parser.parse_args()
    cases = [json.loads(line) for line in FRASES.read_text(encoding="utf-8").splitlines() if line]
    index = SystemIndex.open()
    base: list[dict[str, Any]] = []
    for case in cases:
        if "tipo" in case:
            continue
        calls, text, path = run(case["frase"], index)
        if path == "router" and judge(case, calls, text)[0]:
            base.append(case)
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    fails: list[str] = []
    exported: list[dict[str, Any]] = []
    for case in base:
        for name, make in VARIANTS.items():
            said = make(case["frase"])
            variant = {**case, "frase": said}
            calls, text, path = run(said, index)
            ok, why = judge(variant, calls, text)
            if path != "router":
                ok, why = False, f"va por {path}" + (f" ({why})" if why else "")
            totals[name][0] += ok
            totals[name][1] += 1
            exported.append(variant)
            if not ok:
                fails.append(f"| {name} | {said} | {why} |")
    good = sum(t[0] for t in totals.values())
    total = sum(t[1] for t in totals.values())
    lines = [
        f"# Batería de voz · {datetime.now():%Y-%m-%d %H:%M}",
        "",
        f"Frases del router de partida: {len(base)}. Variantes: {total}. "
        f"**Mismo resultado: {good}/{total} ({100 * good // max(total, 1)} %)**.",
        "",
        "| Variante | Acierto |",
        "| --- | --- |",
        *(f"| {n} | {t[0]}/{t[1]} |" for n, t in totals.items()),
        "",
        "## Fallos",
        "",
        "| Variante | Lo transcrito | Por qué |",
        "| --- | --- | --- |",
        *fails,
    ]
    report = "\n".join(lines) + "\n"
    print(report)
    if args.informe:
        args.informe.write_text(report, encoding="utf-8")
    if args.exportar:
        args.exportar.write_text(
            "".join(json.dumps(v, ensure_ascii=False) + "\n" for v in exported), encoding="utf-8"
        )
    return 0 if good == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
