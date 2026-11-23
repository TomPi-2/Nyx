r"""Batería de audio (plan «Cerebro 2», C0): la cadena real de Nyx con tu voz, sin ejecutar nada.

Cada frase grabada con `record_battery.py` pasa por el pipeline de verdad (detección de voz,
«Nyx», Whisper, router, LLM, pausas y ventana de seguimiento) **al ritmo real**, en cada
condición (limpio y mezclada con los fondos de `record_background.py`). El ejecutor solo apunta
lo que haría: no se abre, cierra ni borra nada.

Mide cada etapa por separado:

- activación (no se activó / se activó sin deber) y, con los fondos solos, activaciones
  falsas por hora;
- fin de frase: cortes antes de acabar y esperas de más;
- Whisper: errores de palabras (WER) y nombres bien oídos;
- qué hizo: bien / preguntó / mal (actuó y no debía: lo peor) / nada;
- latencias (de acabar de hablar a hacer o decir algo) y recursos (CPU, RAM, gráfica, VRAM).

    uv run python scripts/audio_battery.py                      # todo (~12 s por frase y fondo)
    uv run python scripts/audio_battery.py --condiciones limpio # solo sin fondo
    uv run python scripts/audio_battery.py --solo pausa a_medias --max 20
    uv run python scripts/audio_battery.py --informe ../docs/benchmarks/audio-base.md

Mejor con Nyx cerrado (bandeja → Salir): así los recursos son solo los de la batería.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import sqlite3
import statistics
import sys
import tempfile
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from record_battery import FOLDER, nyx_running

from nyx.audio.capture import FRAME_S, FRAME_SAMPLES, SAMPLE_RATE
from nyx.audio.vad import SileroVAD
from nyx.bench import locate
from nyx.bench.audio import Audio, level_db, read_wav
from nyx.bench.guion import Item, load
from nyx.bench.harness import (
    Bench,
    BenchCapture,
    DryExecutor,
    NullPlayer,
    SilentTTS,
    TimedSTT,
    Trace,
    background_stream,
)
from nyx.bench.metrics import Observed, Verdict, judge, percentile, strip_wake, wer
from nyx.bench.resmon import ResourceMonitor
from nyx.brain.answers import Answers
from nyx.brain.ollama import OllamaEngine
from nyx.brain.phrases import PhraseBook
from nyx.brain.router import refusal, route, written_command
from nyx.brain.select import ToolSelector, tools_budget
from nyx.brain.service import Brain
from nyx.brain.shortcuts import ShortcutStore
from nyx.bus import EventBus
from nyx.index.aliases import normalize
from nyx.index.service import SystemIndex
from nyx.models import MODELS
from nyx.paths import local_dir
from nyx.pipeline import STT_PROMPT, VERIFY_CLIP_S, Pipeline
from nyx.services import own_wake_word
from nyx.settings.model import load_settings
from nyx.stt.normalize import has_wake_word
from nyx.stt.whisper_server import WhisperServer
from nyx.tools.base import ToolContext
from nyx.tools.registry import default_registry
from nyx.wake.activations import ActivationLog
from nyx.wake.custom import WakePhrase

BACKGROUNDS = FOLDER / "fondos"
SNR_GAME_DB = 10.0  # altavoces: el juego 10 dB por debajo de la voz
SNR_MUSIC_DB = 5.0  # la música, más alta (5 dB)
LONG_WAIT_S = 1.0  # esperar más de esto tras acabar de hablar cuenta como «espera de más»
CUT_MARGIN_S = 0.15  # dar la frase por acabada antes de esto = cortar al usuario
REFRACTORY_S = 2.0  # escaneo de fondos: tras una activación, no se cuenta otra en 2 s


@dataclass
class Condition:
    name: str
    audio: Audio | None  # el fondo ya con su volumen final (None = limpio)
    how: str


def conditions(
    wanted: list[str] | None, speech_db: float, backgrounds: Path = BACKGROUNDS
) -> list[Condition]:
    """Limpio y una por fondo grabado. Los de la salida se ajustan al volumen de tu voz."""
    found = [Condition("limpio", None, "sin fondo")]
    for path in sorted(backgrounds.glob("*.wav")):
        audio = read_wav(path)
        kind, _, name = path.stem.partition("-")
        if kind == "micro":
            found.append(Condition(f"micro-{name}", audio, "micro tal cual"))
        elif kind == "salida":
            snr = SNR_MUSIC_DB if "musica" in name or "music" in name else SNR_GAME_DB
            gain_db = speech_db - snr - level_db(audio)
            scaled = np.clip(audio.astype(np.float64) * 10 ** (gain_db / 20), -32768, 32767)
            found.append(
                Condition(
                    f"altavoces-{name}",
                    scaled.astype(np.int16),
                    f"salida de audio {snr:g} dB por debajo de la voz",
                )
            )
    if wanted:
        found = [c for c in found if c.name in wanted or c.name.split("-")[0] in wanted]
    return found


def speech_end(clip: Audio, vad: SileroVAD) -> float | None:
    """Cuándo dejó de hablar (último bloque con voz según Silero) en la grabación limpia."""
    vad.reset()
    last = None
    for i in range(clip.size // FRAME_SAMPLES):
        if vad(clip[i * FRAME_SAMPLES : (i + 1) * FRAME_SAMPLES]) >= 0.5:
            last = i
    return None if last is None else (last + 1) * FRAME_S


def shortcuts_copy(folder: Path) -> ShortcutStore:
    """Tus atajos aprendidos, en una copia: la batería los usa pero no aprende ni olvida."""
    copy = folder / "shortcuts.db"
    src_path = local_dir() / "shortcuts.db"
    if src_path.exists():
        src = sqlite3.connect(src_path)
        dst = sqlite3.connect(copy)
        src.backup(dst)
        src.close()
        dst.close()
    return ShortcutStore(copy)


async def wake_scan(
    name: str, audio: Audio, engine: Any, stt: WhisperServer
) -> tuple[float, int, int, list[str]]:
    """Fondo solo: (segundos, saltos del detector, activaciones falsas tras Whisper, oído)."""
    clear = getattr(engine, "clear", None)
    if callable(clear):
        clear()
    engine.reset()
    ring: list[Audio] = []
    keep = int(VERIFY_CLIP_S / FRAME_S) + 1
    raw = 0
    false: list[str] = []
    quiet_until = -1.0
    for i in range(audio.size // FRAME_SAMPLES):
        frame = audio[i * FRAME_SAMPLES : (i + 1) * FRAME_SAMPLES]
        ring = [*ring[-(keep - 1) :], frame]
        t = (i + 1) * FRAME_S
        if not engine.process(frame) or t < quiet_until:
            continue
        raw += 1
        text = await stt.transcribe(np.concatenate(ring), prompt=STT_PROMPT)
        if has_wake_word(text):
            false.append(f"{t:.0f} s «{text}»")
        quiet_until = t + REFRACTORY_S
        engine.reset()
    return audio.size / SAMPLE_RATE, raw, len(false), false


def ok(item: Item, verdict: Verdict) -> bool:
    return verdict is Verdict.BIEN or (verdict is Verdict.PREGUNTO and item.tipo == "preguntar")


def name_heard(item: Item, transcript: str) -> bool | None:
    """En «nombre»: ¿está el nombre esperado en lo transcrito? (None si no aplica)."""
    if item.categoria != "nombre":
        return None
    target = str(item.args.get("name") or item.args.get("target") or "")
    words = normalize(target).replace(".", " ").split()
    text = normalize(transcript).replace(" ", "")
    return bool(words) and all(w.replace(" ", "") in text for w in words[:2])


def record(item: Item, cond: str, trace: Trace) -> dict[str, Any]:
    seen = Observed(trace.activated, [(n, a) for _, n, a in trace.calls], trace.reply)
    verdict = judge(item.expected, seen)
    errors, ref_words = wer(item.frase.replace("…", " "), trace.transcript)
    wait = (
        trace.listen_end - trace.speech_end
        if trace.listen_end is not None and trace.speech_end is not None
        else None
    )
    first = trace.first_output
    return {
        "id": item.id,
        "categoria": item.categoria,
        "condicion": cond,
        "frase": item.frase,
        "esperado": item.expected,
        "veredicto": verdict.value,
        "ok": ok(item, verdict),
        "activada": trace.activated,
        "transcrito": trace.transcript,
        "transcrito_bruto": trace.raw_transcript,
        "despues": trace.later,
        "otro_idioma": trace.foreign,
        "wer": [errors, ref_words] if trace.transcript or trace.activated else None,
        "nombre_oido": name_heard(item, trace.transcript),
        "camino": trace.path,
        "llamadas": [[n, a] for _, n, a in trace.calls],
        "respuesta": trace.reply,
        "fin": trace.end_reason,
        "espera_s": None if wait is None else round(wait, 3),
        "latencia_s": (
            round(first - trace.speech_end, 3)
            if first is not None and trace.speech_end is not None
            else None
        ),
        "whisper": len(trace.stt_calls),
        "whisper_ms": round(sum(ms for _, ms, _, _ in trace.stt_calls)),
        "verificaciones": len(trace.verifications),
    }


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:.0f} %" if d else "—"


def ms(values: list[float]) -> str:
    if not values:
        return "—"
    return f"{percentile(values, 50) * 1000:.0f} / {percentile(values, 95) * 1000:.0f} ms"


def summarize(rows: list[dict[str, Any]], items: dict[str, Item]) -> list[str]:
    lines = [
        "| Condición | Frases | Acierto | **Mal** | Nada | No se activó | Sin deber | WER "
        "| Nombres | Cortes | Esperas > 1 s | Latencia router (p50/p95) "
        "| Latencia LLM (p50/p95) | Whisper por frase |",
        "| --- " * 14 + "|",
    ]
    for cond, group in _by(rows, "condicion").items():
        n = len(group)
        v = Counter(r["veredicto"] for r in group)
        werr = [r["wer"] for r in group if r["wer"] and items[r["id"]].tipo != "ignorar"]
        wer_txt = pct(sum(e for e, _ in werr), sum(w for _, w in werr))
        names = [r["nombre_oido"] for r in group if r["nombre_oido"] is not None]
        turns = [
            r for r in group if r["espera_s"] is not None and items[r["id"]].categoria != "a_medias"
        ]
        cuts = sum(1 for r in turns if r["espera_s"] < -CUT_MARGIN_S and r["fin"] != "max_length")
        long_waits = sum(1 for r in turns if r["espera_s"] > LONG_WAIT_S)
        lat_router = [
            r["latencia_s"]
            for r in group
            if r["latencia_s"] is not None and r["camino"].startswith("router")
        ]
        lat_llm = [
            r["latencia_s"] for r in group if r["latencia_s"] is not None and r["camino"] == "llm"
        ]
        whisper = statistics.mean(r["whisper"] for r in group) if group else 0
        lines.append(
            f"| {cond} | {n} | **{pct(sum(r['ok'] for r in group), n)}** | **{v['mal']}** "
            f"| {v['nada']} | {v['no_activo']} | {v['sin_deber']} | {wer_txt} "
            f"| {sum(1 for x in names if x)}/{len(names)} | {cuts}/{len(turns)} "
            f"| {long_waits}/{len(turns)} | {ms(lat_router)} | {ms(lat_llm)} | {whisper:.1f} |"
        )
    return lines


def by_category(rows: list[dict[str, Any]]) -> list[str]:
    conds = list(_by(rows, "condicion"))
    lines = ["| Tipo | " + " | ".join(conds) + " |", "| --- " * (len(conds) + 1) + "|"]
    for cat, group in sorted(_by(rows, "categoria").items()):
        cells = []
        for cond in conds:
            sub = [r for r in group if r["condicion"] == cond]
            mal = sum(r["veredicto"] == "mal" for r in sub)
            cells.append(
                f"{sum(r['ok'] for r in sub)}/{len(sub)}" + (f" ({mal} mal)" if mal else "")
            )
        lines.append(f"| {cat} | " + " | ".join(cells) + " |")
    return lines


def _by(rows: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        out[r[key]].append(r)
    return out


def cell(text: Any, limit: int = 90) -> str:
    flat = " ".join(str(text).split()).replace("|", "/")
    return flat[:limit]


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--condiciones", nargs="+", help="limpio, micro, altavoces o nombres concretos"
    )
    parser.add_argument("--solo", nargs="+", help="categorías o ids")
    parser.add_argument("--max", type=int, help="como mucho tantas frases (para probar)")
    parser.add_argument("--modelo", help="otro modelo de Ollama")
    parser.add_argument("--umbral", type=float, help="umbral del detector propio")
    parser.add_argument("--sin-fondos-solos", action="store_true", help="sin escanear los fondos")
    parser.add_argument("--informe", type=Path, help="guardar el informe en Markdown (y .jsonl)")
    parser.add_argument("--whisper", type=Path, help="ruta de whisper-server.exe")
    parser.add_argument(
        "--semilla",
        type=int,
        default=1,
        help="semilla del modelo: dos medidas de lo mismo dan lo mismo (0 = sin semilla)",
    )
    parser.add_argument(
        "--carpeta", type=Path, default=FOLDER, help="otra carpeta de grabaciones (con fondos/)"
    )
    args = parser.parse_args()

    items_all = load()
    folder: Path = args.carpeta
    recorded = {p.stem for p in folder.glob("*.wav")}  # noqa: ASYNC240 (al empezar, una vez)
    items = [i for i in items_all if i.id in recorded]
    if args.solo:
        items = [i for i in items if i.categoria in args.solo or i.id in args.solo]
    # Las de un grupo van juntas: si falta una, fuera el grupo entero.
    groups = defaultdict(list)
    for it in items_all:
        if it.grupo:
            groups[it.grupo].append(it.id)
    items = [i for i in items if not i.grupo or all(x in recorded for x in groups[i.grupo])]
    if args.max:
        items = items[: args.max]
    if not items:
        print(f"No hay frases grabadas en {folder}: usa scripts/record_battery.py")
        return 1
    clips = {i.id: read_wav(folder / f"{i.id}.wav") for i in items}
    speech_db = statistics.median(level_db(c, active_only=True) for c in clips.values())
    conds = conditions(args.condiciones, speech_db, folder / "fondos")
    eta = sum(c.size for c in clips.values()) / SAMPLE_RATE + len(items) * 9
    print(
        f"{len(items)} frases × {len(conds)} condiciones ({', '.join(c.name for c in conds)}). "
        f"Unos {eta * len(conds) / 60:.0f} min."
    )
    nyx_open = bool(nyx_running())
    if nyx_open:
        print("Aviso: Nyx está abierto; los recursos medidos incluyen los suyos.")

    settings = load_settings()
    model = args.modelo or settings.llm.model
    llm = OllamaEngine(
        settings.llm.host,
        model,
        keep_alive=settings.llm.keep_alive,
        num_ctx=settings.llm.num_ctx,
        timeout_s=max(30.0, settings.llm.timeout_s),
    )
    registry = default_registry()
    brain = Brain(
        llm,
        tone=settings.responses.tone,
        selector=ToolSelector(registry, budget_chars=tools_budget(settings.llm.num_ctx)),
    )
    index = SystemIndex.open()
    brain.reroute = lambda text: written_command(text, index)
    whisper_path = locate.whisper_server(args.whisper, settings)
    if whisper_path is None:
        print("No encuentro whisper-server.exe: pásalo con --whisper")
        return 1
    whisper = WhisperServer(
        whisper_path,
        settings.stt.model,
        language=settings.stt.language,
        gpu=settings.stt.gpu,
    )
    await whisper.start()
    await brain.warmup()
    llm.seed = args.semilla or None
    stt = TimedSTT(whisper)
    vad = SileroVAD(MODELS["vad"].path())
    end_vad = SileroVAD(MODELS["vad"].path())
    wake = own_wake_word(settings)
    if args.umbral is not None:
        wake.threshold = args.umbral
    tmp = Path(tempfile.mkdtemp(prefix="nyx-bateria-"))
    shortcuts = shortcuts_copy(tmp)
    phrases = PhraseBook()
    dry = DryExecutor(registry, ToolContext(index=index, settings=settings), phrases=phrases)
    capture = BenchCapture()
    tts = SilentTTS()
    bus = EventBus()
    pipeline = Pipeline(
        bus,
        brain,
        listen=settings.listen,
        wake_prebuffer_s=settings.wake.prebuffer_s,
        capture=capture,  # type: ignore[arg-type]
        wake=wake,
        vad=vad,
        stt=stt,
        tts=tts,
        player=NullPlayer(),  # type: ignore[arg-type]
        router=lambda text: route(text, index),
        refuse=lambda text: refusal(text, index),
        executor=dry,
        shortcuts=shortcuts,
        activations=ActivationLog(tmp / "activaciones", tmp / "activacion.json"),
        wake_phrase=WakePhrase(),
        phrases=phrases,
        answers=Answers(settings.responses.tone),
    )

    async def no_context() -> str:
        return ""  # sin la ventana activa real: la batería no depende de qué hay abierto

    pipeline._context = no_context  # type: ignore[method-assign]
    bench = Bench(pipeline, capture=capture, executor=dry, tts=tts, stt=stt)

    rows: list[dict[str, Any]] = []
    scans: list[tuple[str, float, int, int, list[str]]] = []
    t0 = time.perf_counter()
    monitor = ResourceMonitor().start()
    try:
        for cond in conds:
            print(f"\n== {cond.name} ({cond.how})")
            stream = background_stream(cond.audio)
            for k, item in enumerate(items):
                clip = clips[item.id]
                if cond.audio is not None:
                    seg = stream(clip.size).astype(np.int32)
                    mixed = np.clip(clip.astype(np.int32) + seg, -32768, 32767).astype(np.int16)
                else:
                    mixed = clip
                nxt = items[k + 1] if k + 1 < len(items) else None
                then_followup = bool(item.grupo and nxt is not None and nxt.grupo == item.grupo)
                follows = bool(item.grupo and k > 0 and items[k - 1].grupo == item.grupo)
                if not follows:
                    brain.memory.clear()
                trace = await bench.run(
                    mixed,
                    stream,
                    speech_end_s=speech_end(clip, end_vad),
                    lead_s=0.4 if follows else 2.0,
                    then_followup=then_followup,
                )
                row = record(item, cond.name, trace)
                rows.append(row)
                mark = "✓" if row["ok"] else ("✗✗" if row["veredicto"] == "mal" else "✗")
                print(
                    f"{mark:2} {item.id} {row['veredicto']:9} «{cell(trace.transcript, 60)}» → "
                    f"{cell(row['llamadas'] or row['respuesta'], 70)}"
                )
            if cond.audio is not None and not args.sin_fondos_solos:
                secs, raw, false, heard = await wake_scan(cond.name, cond.audio, wake, whisper)
                scans.append((cond.name, secs, raw, false, heard))
    finally:
        monitor.stop()
        bench.close()
        await pipeline.close()
        await whisper.stop()
        await llm.aclose()
        shortcuts.close()
        index.close()
    elapsed = time.perf_counter() - t0

    by_id = {i.id: i for i in items}
    lines = [
        f"# Batería de audio · {platform.node()} · {datetime.now():%Y-%m-%d %H:%M}",
        "",
        f"Modelo: `{model}`. Whisper: `{Path(str(settings.stt.model)).name}`. Detector: propio "
        f"(umbral {wake.threshold:.2f}). Frases: {len(items)}. Duración: {elapsed / 60:.0f} min."
        + (" Nyx estaba abierto." if nyx_open else ""),
        "",
        "Acierto = hizo lo esperado (o preguntó cuando debía preguntar). **Mal** = actuó y no "
        "debía o hizo otra cosa (lo peor). Nada = ni actuó ni preguntó. Cortes = dio la frase "
        f"por terminada > {CUT_MARGIN_S:g} s antes de que acabaras. Latencia = de acabar de hablar "
        "a hacer o decir algo. Las acciones rojas no piden confirmación en la batería.",
        "",
        "## Resumen",
        "",
        *summarize(rows, by_id),
        "",
        "## Por tipo de frase",
        "",
        *by_category(rows),
        "",
    ]
    if scans:
        lines += [
            "## Activaciones falsas con el fondo solo",
            "",
            "| Fondo | Minutos | Saltos del detector | Falsas tras Whisper | Por hora |",
            "| --- | --- | --- | --- | --- |",
        ]
        for name, secs, raw, false, _ in scans:
            hours = secs / 3600
            lines.append(
                f"| {name} | {secs / 60:.1f} | {raw} ({raw / hours:.0f}/h) | {false} "
                f"| {false / hours:.1f} |"
            )
        lines += [""]
        for name, _, _, _, heard in scans:
            if heard:
                lines += [f"- {name}: " + "; ".join(heard[:8])]
        lines += [""]
    lines += ["## Recursos (toda la batería)", "", monitor.report()]
    failures = [r for r in rows if not r["ok"]]
    if failures:
        lines += [
            "## Fallos",
            "",
            "| Id | Condición | Veredicto | Frase | Oyó | Hizo |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        order = {"mal": 0, "sin_deber": 1, "no_activo": 2, "nada": 3, "pregunto": 4}
        for r in sorted(failures, key=lambda r: (order.get(r["veredicto"], 9), r["id"])):
            got = r["llamadas"] or (f"«{r['respuesta']}»" if r["respuesta"] else "—")
            lines.append(
                f"| {r['id']} | {r['condicion']} | {r['veredicto']} | {cell(r['frase'], 60)} "
                f"| {cell(strip_wake(r['transcrito']) or '—', 60)} | {cell(got)} |"
            )
    text = "\n".join(lines) + "\n"
    print()
    print(text.split("## Fallos")[0])
    if args.informe:
        args.informe.parent.mkdir(parents=True, exist_ok=True)
        args.informe.write_text(text, encoding="utf-8")
        detail = args.informe.with_suffix(".jsonl")
        detail.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
        )
        print(f"Informe: {args.informe} (detalle de cada frase: {detail.name})")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
