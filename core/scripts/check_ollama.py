"""Prueba técnica de la fase 1: Ollama en la GPU.

Mide, para cada modelo candidato:
- tiempo de carga y VRAM usada (y si cabe entero en la GPU),
- tiempo hasta el primer token y tokens por segundo en una respuesta en español,
- si elige la herramienta correcta en tres peticiones típicas.

Uso (desde core/):  uv run python scripts/check_ollama.py [--models qwen2.5:7b llama3.1:8b]
Objetivo de la SPEC (sección 14): primera palabra hablada en < 1,5 s.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from typing import Any

import httpx
from hwinfo import hardware, save_report

DEFAULT_MODELS = ["qwen2.5:7b", "llama3.1:8b"]
SYSTEM = "Eres Nyx, un asistente de voz para Windows. Responde en español, breve y sin relleno."
QUESTION = "¿Cómo se dice hola en alemán? Responde en una sola frase."

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": "Abre una aplicación o juego. Ej.: «abre Visual Studio Code».",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_volume",
            "description": "Cambia el volumen general (0–100) o lo silencia.",
            "parameters": {
                "type": "object",
                "properties": {"level": {"type": "integer"}, "mute": {"type": "boolean"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_alarm",
            "description": "Pone una alarma a una hora (formato HH:MM).",
            "parameters": {
                "type": "object",
                "properties": {"time": {"type": "string"}},
                "required": ["time"],
            },
        },
    },
]
TOOL_CASES = [
    ("Abre Visual Studio Code", "open_app"),
    ("Baja el volumen al 20", "set_volume"),
    ("Pon una alarma a las diez cincuenta", "set_alarm"),
]


def load(client: httpx.Client, model: str) -> dict[str, Any]:
    t0 = time.perf_counter()
    client.post("/api/generate", json={"model": model, "prompt": "", "keep_alive": "10m"})
    load_s = time.perf_counter() - t0
    running = client.get("/api/ps").json().get("models", [])
    entry = next((m for m in running if m.get("name") == model or m.get("model") == model), {})
    size, vram = entry.get("size", 0), entry.get("size_vram", 0)
    return {
        "load_s": round(load_s, 2),
        "vram_gb": round(vram / 2**30, 2),
        "gpu_percent": round(100 * vram / size) if size else None,
    }


def first_token(client: httpx.Client, model: str) -> dict[str, float]:
    body = {
        "model": model,
        "stream": True,
        "keep_alive": "10m",
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": QUESTION}],
    }
    t0 = time.perf_counter()
    ttft: float | None = None
    final: dict[str, Any] = {}
    with client.stream("POST", "/api/chat", json=body) as resp:
        for line in resp.iter_lines():
            if not line:
                continue
            chunk = json.loads(line)
            if ttft is None and chunk.get("message", {}).get("content"):
                ttft = time.perf_counter() - t0
            if chunk.get("done"):
                final = chunk
    eval_s = final.get("eval_duration", 0) / 1e9
    return {
        "ttft_s": round(ttft or 0.0, 3),
        "tokens_per_s": round(final.get("eval_count", 0) / eval_s, 1) if eval_s else 0.0,
    }


def tool_calls(client: httpx.Client, model: str) -> dict[str, Any]:
    hits, times = 0, []
    for prompt, expected in TOOL_CASES:
        body = {
            "model": model,
            "stream": False,
            "keep_alive": "10m",
            "tools": TOOLS,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": prompt},
            ],
        }
        t0 = time.perf_counter()
        msg = client.post("/api/chat", json=body).json().get("message", {})
        times.append(time.perf_counter() - t0)
        calls = msg.get("tool_calls") or []
        if calls and calls[0].get("function", {}).get("name") == expected:
            hits += 1
    return {
        "tool_hits": f"{hits}/{len(TOOL_CASES)}",
        "tool_call_s": round(statistics.median(times), 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--host", default="http://127.0.0.1:11434")
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()

    client = httpx.Client(base_url=args.host, timeout=300)
    try:
        version = client.get("/api/version").json().get("version")
    except httpx.HTTPError:
        print("Ollama no responde. Instálalo desde https://ollama.com y ábrelo.", file=sys.stderr)
        return 1
    installed = {m["name"] for m in client.get("/api/tags").json().get("models", [])}

    report: dict[str, Any] = {"hardware": hardware(), "ollama": version, "models": {}}
    for model in args.models:
        if model not in installed:
            print(f"· {model}: no instalado (ollama pull {model})")
            continue
        print(f"· {model}: cargando…", flush=True)
        result = load(client, model)
        runs = [first_token(client, model) for _ in range(args.runs)]
        result["ttft_s"] = statistics.median(r["ttft_s"] for r in runs)
        result["tokens_per_s"] = statistics.median(r["tokens_per_s"] for r in runs)
        result |= tool_calls(client, model)
        result["meets_ttft_1_5s"] = result["ttft_s"] < 1.5
        report["models"][model] = result
        print(f"  {result}")
        client.post("/api/generate", json={"model": model, "keep_alive": 0})  # liberar VRAM

    path = save_report("ollama", report)
    print(f"Informe guardado en {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
