"""Cuánto cuesta el prefijo fijo del cerebro (0.6, tarea 6.18).

El prompt de sistema y las herramientas van en cada petición. Este script mide, con el modelo
real:
- tokens del prefijo (sistema + herramientas) y lo que ocupa cada herramienta;
- tiempo hasta el primer token con la caché del prefijo fría y caliente;
- cuánto queda del contexto (`num_ctx`) para la memoria, el contexto y la respuesta.

Uso (desde core/, con Ollama abierto):
    uv run python scripts/prompt_cost.py [--model qwen2.5:7b] [--informe ruta.md]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from nyx.brain.prompts import SYSTEM
from nyx.settings.model import load_settings
from nyx.tools.registry import default_registry

HOST = "http://127.0.0.1:11434"
QUESTION = "¿Cuánto es 17 por 23?"


def chat(model: str, system: str, tools: list[dict[str, Any]], num_ctx: int) -> dict[str, Any]:
    """Una petición sin streaming; devuelve los contadores de Ollama y el primer token."""
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
    with httpx.stream("POST", f"{HOST}/api/chat", json=body, timeout=120) as resp:
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
    num_ctx = settings.llm.num_ctx
    tools = default_registry().schemas()

    # Prefijo nuevo (caché fría): un comentario único al final del sistema obliga a evaluarlo.
    cold = chat(args.model, f"{SYSTEM}\n<!-- {uuid.uuid4()} -->", tools, num_ctx)
    warm = chat(args.model, f"{SYSTEM}\n<!-- igual -->", tools, num_ctx)
    warm = chat(args.model, f"{SYSTEM}\n<!-- igual -->", tools, num_ctx)  # ya en caché
    bare = chat(args.model, f"{SYSTEM}\n<!-- {uuid.uuid4()} -->", [], num_ctx)

    total = int(cold.get("prompt_eval_count", 0))
    system_only = int(bare.get("prompt_eval_count", 0))
    tools_tokens = total - system_only
    sizes = {t["function"]["name"]: len(json.dumps(t, ensure_ascii=False)) for t in tools}
    chars = sum(sizes.values())
    lines = [
        f"# Coste del prefijo · {args.model} · {len(tools)} herramientas",
        "",
        f"- Tokens del prefijo (sistema + herramientas + pregunta): **{total}** de {num_ctx} "
        f"({total * 100 // num_ctx} % del contexto).",
        f"- Sistema y pregunta sin herramientas: {system_only}. Herramientas: **{tools_tokens}** "
        f"(~{tools_tokens // max(1, len(tools))} por herramienta).",
        f"- Primer token con la caché fría: **{cold['first_s']:.2f} s**; caliente: "
        f"**{warm['first_s']:.2f} s**.",
        "",
        "| Herramienta | Tokens (aprox.) |",
        "| --- | --- |",
    ]
    for name, size in sorted(sizes.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {name} | {round(tools_tokens * size / chars)} |")
    report = "\n".join(lines) + "\n"
    print(report)
    if args.informe:
        args.informe.write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
