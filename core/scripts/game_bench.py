"""Cuánto le cuesta Nyx a un juego (0.5, bloque 3; docs/HOJA-DE-RUTA.md §1.1).

Con el juego abierto, mide los fotogramas con PresentMon (Intel, licencia MIT) en varias
configuraciones del cerebro mientras simula a Nyx pensando: cada pocos segundos transcribe
una frase con el Whisper de Nyx y responde una pregunta con el prompt y las herramientas
reales de Nyx. Así se ve qué cerebro se puede usar en partida sin tirones.

Configuraciones (`--configs`):
- `sin`: el juego solo (la referencia).
- `<modelo>@gpu` / `<modelo>@cpu`: Whisper + una respuesta del LLM cada `--every` s.
- `verificar` (C0, 2026-11-23): solo las comprobaciones de «Nyx» (Whisper con 2 s de audio,
  sin LLM), como las activaciones falsas de los registros. El LLM queda cargado, sin usarse.
- `whisper`: solo la transcripción de una frase entera, sin LLM.
- `llamacpp@gpu` / `llamacpp@cpu` (C5.1): como `<modelo>@gpu`, con llama-server en vez de
  Ollama. Para comparar: `--configs sin nyx-r2:7b@gpu llamacpp@gpu`.

Antes:
1. Descarga PresentMon (la versión de consola, «PresentMon-…-x64.exe») de
   https://github.com/GameTechDev/PresentMon/releases
2. Cierra Nyx (bandeja → Salir): si no, su cerebro ya estaría ocupando la gráfica.
3. Abre una terminal **como administrador** (PresentMon lo necesita para leer los
   fotogramas) y entra en core/.

Uso:
    uv run python scripts/game_bench.py --presentmon C:\\ruta\\PresentMon.exe \\
        --process RocketLeague.exe

Al empezar tienes 20 s para entrar en el juego (por ejemplo, en «Juego libre»). Cada
configuración dura ~70 s; un pitido marca el cambio y dos el final. Juega igual en todas.
El informe se guarda en docs/benchmarks/partida-<equipo>-<fecha>.md (y .json).
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import csv
import ctypes
import platform
import statistics
import subprocess
import sys
import tempfile
import time
import wave
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import numpy as np
from check_whisper import synthesize
from hwinfo import REPORTS_DIR, hardware, save_report

from nyx.bench import locate
from nyx.bench.resmon import ResourceMonitor
from nyx.brain.base import ChatMessage
from nyx.brain.llamacpp import LlamaCppEngine
from nyx.brain.llamacpp_process import from_settings
from nyx.brain.prompts import SYSTEM
from nyx.settings.model import load_settings
from nyx.stt.whisper_server import WhisperServer
from nyx.tools.registry import default_registry

OLLAMA = "http://127.0.0.1:11434"
# «modelo@gpu» o «modelo@cpu»; «sin» = el juego solo (la referencia).
# Un solo cerebro desde el 2026-11-11 (el 14B, qwen3:4b y el procesador ya se midieron y se
# descartaron): por defecto, el juego solo y el 7B en la gráfica. Se pueden pasar con --configs.
DEFAULT_CONFIGS = ["sin", "verificar", "whisper", "qwen2.5:7b@gpu"]
WHISPER_ONLY = {"verificar", "whisper"}  # sin LLM (el de los ajustes, cargado y quieto)
# «llamacpp@gpu» / «llamacpp@cpu» (C5.1): el cerebro de los ajustes en llama-server en vez de
# Ollama (el .gguf de `llm.model_path` o el bajado en el primer arranque).
LLAMACPP = "llamacpp"
QUESTION = "Explícame en dos frases qué es un agujero negro."
PHRASE = "Nyx, ¿qué tiempo hace mañana en Valencia?"
SPIKE = 2.0  # un fotograma que tarda más del doble que la mediana es un tirón


@dataclass
class Result:
    config: str
    frames: int = 0
    avg_fps: float = 0.0
    low1_fps: float = 0.0  # FPS del 1 % de fotogramas más lentos
    low01_fps: float = 0.0  # y del 0,1 %
    median_ms: float = 0.0
    worst_ms: float = 0.0
    spikes: int = 0
    thinks: int = 0  # veces que «pensó» durante la medida
    think_s: list[float] = field(default_factory=list)  # lo que tardó cada respuesta
    note: str = ""
    nyx_gpu: str = ""  # uso de la gráfica de Whisper y del LLM (media / máx)


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except AttributeError, OSError:
        return False


def beep(times: int = 1) -> None:
    import winsound

    for _ in range(times):
        winsound.Beep(880, 180)
        time.sleep(0.12)


def frame_times(path: Path) -> list[float]:
    """Milisegundos entre fotogramas del CSV de PresentMon (columnas de la v1 o la v2)."""
    with path.open(encoding="utf-8", errors="replace", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return []
    column = next(
        (c for c in ("MsBetweenPresents", "FrameTime", "msBetweenPresents") if c in rows[0]),
        None,
    )
    if column is None:
        raise RuntimeError(f"PresentMon: no encuentro el tiempo por fotograma en {list(rows[0])}")
    out: list[float] = []
    for row in rows:
        with contextlib.suppress(ValueError):
            value = float(row[column])
            if value > 0:
                out.append(value)
    return out


def summarize(result: Result, times: list[float]) -> None:
    if not times:
        result.note = "sin fotogramas: ¿el juego estaba abierto y en primer plano?"
        return
    ordered = sorted(times)
    median = statistics.median(ordered)
    slowest = ordered[-max(1, len(ordered) // 100) :]
    result.frames = len(times)
    result.avg_fps = round(1000 / statistics.fmean(times), 1)
    result.low1_fps = round(1000 / statistics.fmean(slowest), 1)
    result.low01_fps = round(1000 / statistics.fmean(ordered[-max(1, len(ordered) // 1000) :]), 1)
    result.median_ms = round(median, 2)
    result.worst_ms = round(ordered[-1], 1)
    result.spikes = sum(1 for t in times if t > SPIKE * median)


async def unload_all(client: httpx.AsyncClient) -> None:
    """Saca de la memoria todos los modelos de Ollama (cada configuración empieza limpia)."""
    with contextlib.suppress(httpx.HTTPError):
        loaded = (await client.get("/api/ps")).json().get("models", [])
        for m in loaded:
            await client.post("/api/generate", json={"model": m["name"], "keep_alive": 0})


async def installed(client: httpx.AsyncClient) -> set[str]:
    data = (await client.get("/api/tags")).json()
    return {m["name"] for m in data.get("models", [])}


def body(model: str, on_cpu: bool, tools: list[dict[str, Any]], num_ctx: int) -> dict[str, Any]:
    # El mismo contexto que Nyx (llm.num_ctx): la memoria de la gráfica depende de él.
    options: dict[str, Any] = {"num_ctx": num_ctx}
    if on_cpu:
        options["num_gpu"] = 0
    data: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": QUESTION},
        ],
        "tools": tools,
        "stream": True,
        "keep_alive": -1,
        "options": options,
    }
    if model.startswith("qwen3"):
        data["think"] = False  # Nyx no usa el modo de razonamiento para responder rápido
    return data


async def think(
    client: httpx.AsyncClient, stt: WhisperServer | None, pcm: Any, request: dict[str, Any]
) -> float:
    """Una petición como las de Nyx: transcribir y responder. Devuelve lo que tardó."""
    t0 = time.perf_counter()
    if stt is not None:
        await stt.transcribe(pcm)
    async with client.stream("POST", "/api/chat", json=request, timeout=120) as resp:
        async for _ in resp.aiter_lines():
            pass
    return time.perf_counter() - t0


async def think_llama(
    engine: LlamaCppEngine, stt: WhisperServer | None, pcm: Any, tools: list[dict[str, Any]]
) -> float:
    """Lo mismo que `think`, con el cerebro en llama-server (C5.1)."""
    t0 = time.perf_counter()
    if stt is not None:
        await stt.transcribe(pcm)
    messages = [ChatMessage("system", SYSTEM), ChatMessage("user", QUESTION)]
    async for _ in engine.chat(messages, tools=tools):
        pass
    return time.perf_counter() - t0


async def run_config(
    config: str,
    args: argparse.Namespace,
    client: httpx.AsyncClient,
    stt: WhisperServer | None,
    pcm: Any,
    tools: list[dict[str, Any]],
    have: set[str],
    out_dir: Path,
) -> Result:
    result = Result(config)
    request: dict[str, Any] | None = None
    engine: LlamaCppEngine | None = None
    if config in WHISPER_ONLY:
        if stt is None:
            result.note = "sin Whisper"
            return result
        model, where = load_settings().llm.model, "gpu"
    else:
        model, _, where = config.partition("@")
    if model == LLAMACPP:
        server = from_settings(load_settings(), num_ctx=args.contexto, cpu=where == "cpu")
        if not server.model.is_file() or not server.server.is_file():
            result.note = f"falta llama-server o {server.model.name}"
            print(f"  · {config}: {result.note}, se salta")
            return result
        engine = LlamaCppEngine(server, "llama.cpp", timeout_s=120.0)
        print(f"  · {config}: cargando el modelo…")
        await unload_all(client)
        await think_llama(engine, None, pcm, tools)  # carga y calienta antes de medir
    elif config != "sin":
        if model not in have and f"{model}:latest" not in have:
            result.note = f"no instalado (ollama pull {model})"
            print(f"  · {config}: {result.note}, se salta")
            return result
        request = body(model, where == "cpu", tools, args.contexto)
        print(f"  · {config}: cargando el modelo…")
        await unload_all(client)
        await think(client, None, pcm, request)  # carga y calienta antes de medir
    else:
        await unload_all(client)
    csv_path = out_dir / f"{config.replace(':', '_').replace('@', '-')}.csv"
    beep()
    print(f"  · {config}: midiendo {args.seconds} s…")
    pm = await asyncio.create_subprocess_exec(
        str(args.presentmon),
        "--process_name",
        args.process,
        "--output_file",
        str(csv_path),
        "--timed",
        str(args.seconds),
        "--terminate_after_timed",
        "--stop_existing_session",
        "--no_console_stats",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    end = time.monotonic() + args.seconds
    monitor = ResourceMonitor(include_self=False, interval_s=0.25).start()
    if request is not None or engine is not None:
        await asyncio.sleep(2)
        while time.monotonic() < end - 3:
            t0 = time.perf_counter()
            if config == "verificar" and stt is not None:
                await stt.transcribe(pcm[-2 * 16_000 :], prompt="Nyx.")
            elif config == "whisper" and stt is not None:
                await stt.transcribe(pcm)
            elif engine is not None:
                await think_llama(engine, stt, pcm, tools)
            elif request is not None:
                await think(client, stt, pcm, request)
            took = time.perf_counter() - t0
            result.thinks += 1
            result.think_s.append(round(took, 2))
            await asyncio.sleep(max(0.0, args.every - took))
    await pm.wait()
    monitor.stop()
    if engine is not None:
        await engine.unload()  # para llama-server: la siguiente configuración empieza limpia
        await engine.aclose()
    gpu = [g for name, st in monitor.procs.items() if name != "ollama.exe" for g in st.gpu]
    if gpu:
        result.nyx_gpu = f"{statistics.fmean(gpu):.1f} % / {max(gpu):.0f} %"
    try:
        summarize(result, frame_times(csv_path))
    except (OSError, RuntimeError) as exc:
        result.note = str(exc)
    print(f"    {result}")
    return result


def markdown(results: list[Result], hw: dict[str, Any], args: argparse.Namespace) -> str:
    base = next((r for r in results if r.config == "sin" and r.frames), None)
    lines = [
        f"# Nyx en partida · {platform.node()} · {datetime.now():%Y-%m-%d %H:%M}",
        "",
        f"Juego: `{args.process}`. {args.seconds} s por configuración; Nyx «piensa» cada "
        f"{args.every} s (Whisper + una respuesta con el prompt y las herramientas reales). "
        f"Contexto: {args.contexto} tokens.",
        f"Equipo: {hw.get('cpu', '?')}, {hw.get('ram_gb', '?')} GB, "
        f"{', '.join(hw.get('gpus', []))}.",
        "",
        "Objetivo (decisión del 2026-11-11): **menos de un 5 % de FPS medios y el peor "
        "fotograma como mucho 1,5× el del juego solo** mientras Nyx piensa. Tirones: "
        f"fotogramas de más de {SPIKE:g}× la mediana.",
        "",
        "| Configuración | FPS medios | Cambio | 1 % más lento | 0,1 % más lento | Tirones "
        "| Peor fotograma | Respuesta (mediana) | Gráfica de Nyx (media / máx) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in results:
        if not r.frames:
            lines.append(f"| {r.config} | — | — | — | — | — | — | {r.note} | — |")
            continue
        change = f"{(r.avg_fps / base.avg_fps - 1) * 100:+.1f} %" if base and r is not base else "—"
        took = f"{statistics.median(r.think_s):.1f} s" if r.think_s else "—"
        lines.append(
            f"| {r.config} | {r.avg_fps} | {change} | {r.low1_fps} | {r.low01_fps} | {r.spikes} "
            f"| {r.worst_ms} ms | {took} | {r.nyx_gpu or '—'} |"
        )
    return "\n".join(lines) + "\n"


async def main_async(args: argparse.Namespace) -> int:
    settings = load_settings()
    if args.contexto is None:
        args.contexto = settings.llm.num_ctx
    tools = default_registry().schemas()
    tmp = Path(tempfile.mkdtemp(prefix="nyx-bench-"))
    wav = tmp / "frase.wav"
    synthesize(PHRASE, wav)
    with wave.open(str(wav)) as w:
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)

    stt: WhisperServer | None = None
    server = locate.whisper_server(None, settings)
    if args.whisper and server is not None:
        stt = WhisperServer(server, settings.stt.model, gpu=settings.stt.gpu)
        await stt.start()
        print(f"Whisper en {stt.device_name or 'su tarjeta'}")
    elif args.whisper:
        print("Sin Whisper: no encuentro whisper-server.exe")

    results: list[Result] = []
    async with httpx.AsyncClient(base_url=OLLAMA, timeout=300) as client:
        have = await installed(client)
        print(f"Tienes {args.wait} s para entrar en el juego y empezar a jugar…")
        await asyncio.sleep(args.wait)
        for config in args.configs:
            results.append(await run_config(config, args, client, stt, pcm, tools, have, tmp))
        await unload_all(client)
    if stt is not None:
        await stt.stop()
    beep(2)

    hw = hardware()
    report = markdown(results, hw, args)
    data = {"hardware": hw, "process": args.process, "results": [r.__dict__ for r in results]}
    json_path = save_report("partida", data)
    md_path = json_path.with_suffix(".md")
    md_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"Informe: {md_path.relative_to(REPORTS_DIR.parent.parent)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--presentmon", type=Path, required=True, help="PresentMon.exe")
    parser.add_argument("--process", required=True, help="ejecutable del juego")
    parser.add_argument("--configs", nargs="+", default=DEFAULT_CONFIGS)
    parser.add_argument("--seconds", type=int, default=60, help="medida por configuración")
    parser.add_argument("--every", type=float, default=8.0, help="cada cuánto «piensa» Nyx")
    parser.add_argument("--wait", type=int, default=20, help="tiempo para entrar en el juego")
    parser.add_argument("--no-whisper", dest="whisper", action="store_false")
    parser.add_argument(
        "--contexto", type=int, default=None, help="num_ctx (por defecto, el de los ajustes)"
    )
    args = parser.parse_args()
    if not args.presentmon.exists():
        print(f"No encuentro PresentMon en {args.presentmon}", file=sys.stderr)
        return 1
    if not is_admin():
        print(
            "Ábrelo en una terminal como administrador (PresentMon lo necesita).", file=sys.stderr
        )
        return 1
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
