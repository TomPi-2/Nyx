"""Coste de los grupos de herramientas (0.6, tarea 6.20b).

Para cada grupo, con el modelo real: tokens que añade a las fijas y tiempo hasta el primer
token al **cambiar** a él desde otro grupo (la caché de Ollama solo reutiliza el principio
común: sistema + fijas) y con la lista ya en caché. Compara con la lista entera (antes de la
6.20b).

Uso (desde core/, con Ollama abierto y sin nada más usando la gráfica):
    uv run python scripts/groups_bench.py [--informe ../docs/benchmarks/grupos-6.20b.md]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from nyx.brain.prompts import SYSTEM
from nyx.brain.select import ToolSelector
from nyx.settings.model import load_settings
from nyx.tools.registry import default_registry

QUESTION = "¿Cuánto es 17 por 23?"


def chat(
    host: str, model: str, system: str, tools: list[dict[str, Any]], num_ctx: int
) -> dict[str, Any]:
    body = {
        "model": model,
        "stream": True,
        "keep_alive": -1,
        "options": {"num_ctx": num_ctx, "num_predict": 1},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": QUESTION}],
        "tools": tools,
    }
    t0 = time.perf_counter()
    first: float | None = None
    done: dict[str, Any] = {}
    with httpx.stream("POST", f"{host}/api/chat", json=body, timeout=180) as resp:
        for line in resp.iter_lines():
            if not line:
                continue
            chunk = json.loads(line)
            if first is None:
                first = time.perf_counter() - t0
            if chunk.get("done"):
                done = chunk
    done["first_s"] = first or 0.0
    return done


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    settings = load_settings()
    parser.add_argument("--model", default=settings.llm.model)
    parser.add_argument("--informe", type=Path, default=None)
    args = parser.parse_args()
    host, num_ctx = settings.llm.host, settings.llm.num_ctx
    registry = default_registry()
    sel = ToolSelector(registry)
    # Un sistema único para no heredar la caché de otra ejecución; igual en todas las peticiones.
    system = f"{SYSTEM}\n<!-- {uuid.uuid4()} -->"

    def ask(tools: list[dict[str, Any]]) -> dict[str, Any]:
        return chat(host, args.model, system, tools, num_ctx)

    everything = registry.schemas()
    ask(everything)
    all_warm = ask(everything)
    fixed = sel.tools_for(())
    ask(fixed)
    fixed_warm = ask(fixed)
    base_tokens = int(fixed_warm.get("prompt_eval_count", 0))
    rows: list[tuple[str, int, int, float, float]] = []
    switches: list[float] = []
    previous = sel.groups[-1].name
    for group in sel.groups:
        ask(sel.tools_for((previous,)))  # se viene de otro grupo, en caché
        switch = ask(sel.tools_for((group.name,)))
        warm = ask(sel.tools_for((group.name,)))
        tokens = int(warm.get("prompt_eval_count", 0)) - base_tokens
        rows.append((group.name, len(group.tools), tokens, switch["first_s"], warm["first_s"]))
        switches.append(switch["first_s"])
        previous = group.name
    # Vuelta a todas: cuánto cuesta lo de antes al cambiar desde un grupo.
    all_switch = ask(everything)

    lines = [
        f"# Coste de los grupos · {args.model} · num_ctx {num_ctx}",
        "",
        f"- Todas las herramientas ({len(everything)}): **{all_warm.get('prompt_eval_count')}** "
        f"tokens de prefijo; primer token en caché {all_warm['first_s']:.2f} s, al volver a "
        f"ellas desde un grupo {all_switch['first_s']:.2f} s.",
        f"- Solo las fijas ({len(fixed)}): **{base_tokens}** tokens; en caché "
        f"{fixed_warm['first_s']:.2f} s.",
        f"- Cambio de grupo: mediana **{statistics.median(switches):.2f} s**, peor "
        f"{max(switches):.2f} s.",
        "",
        "| Grupo | Herramientas | Tokens sobre las fijas | Primer token al cambiar | En caché |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name, count, tokens, switch_s, warm_s in rows:
        lines.append(f"| {name} | {count} | {tokens} | {switch_s:.2f} s | {warm_s:.2f} s |")
    text = "\n".join(lines) + "\n"
    print(text)
    if args.informe:
        args.informe.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
