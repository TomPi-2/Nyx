r"""Mide la palabra de activación con las grabaciones de record_samples.py (fase 4a).

Para cada grabación hace lo mismo que Nyx: el detector escucha bloque a bloque y, si salta,
whisper revisa los últimos 2 s (SPEC sección 4.4). Cuenta:

- positivos: % de veces que «Nyx» activa (por tipo: cerca, lejos, bajito…);
- parecidas: cuántas palabras parecidas activan sin querer;
- continuo: activaciones falsas por hora de uso normal.

    uv run python scripts/wake_eval.py
    uv run python scripts/wake_eval.py --informe ../docs/benchmarks/activacion-vosk.md

Más adelante, `--motor` elegirá el detector (fase 4b: el modelo propio).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
import wave
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import numpy.typing as npt

from nyx.audio.capture import FRAME_S, FRAME_SAMPLES, SAMPLE_RATE, Frame
from nyx.models import MODELS
from nyx.paths import local_dir
from nyx.pipeline import STT_PROMPT, VERIFY_CLIP_S
from nyx.services import whisper_server_path
from nyx.settings.model import load_settings
from nyx.stt.normalize import has_wake_word
from nyx.stt.whisper_server import WhisperServer
from nyx.wake.base import WakeWordEngine
from nyx.wake.vosk_engine import VoskWakeWord

RECORDINGS = local_dir() / "training" / "grabaciones"
REFRACTORY_S = 2.0  # tras una activación, Nyx escucha la orden: no se cuenta otra


@dataclass
class Trigger:
    file: str
    at_s: float
    verified: bool
    heard: str


@dataclass
class Summary:
    seconds: float = 0.0
    triggers: list[Trigger] = field(default_factory=list)


def read_wav(path: Path) -> npt.NDArray[np.int16]:
    with wave.open(str(path), "rb") as w:
        assert w.getframerate() == SAMPLE_RATE and w.getnchannels() == 1, path
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)


async def scan(
    path: Path, engine: WakeWordEngine, stt: WhisperServer, *, tail_s: float = 1.0
) -> tuple[list[Trigger], float]:
    """Activaciones en un archivo (con verificación de whisper) y su duración."""
    audio = read_wav(path)
    audio = np.concatenate([audio, np.zeros(int(tail_s * SAMPLE_RATE), dtype=np.int16)])
    engine.reset()
    ring: deque[Frame] = deque(maxlen=int(VERIFY_CLIP_S / FRAME_S) + 1)
    triggers: list[Trigger] = []
    quiet_until = -1.0
    for i in range(len(audio) // FRAME_SAMPLES):
        frame = audio[i * FRAME_SAMPLES : (i + 1) * FRAME_SAMPLES]
        ring.append(frame)
        t = (i + 1) * FRAME_S
        if not engine.process(frame) or t < quiet_until:
            continue
        clip = np.concatenate(list(ring))
        text = await stt.transcribe(clip, prompt=STT_PROMPT)
        triggers.append(Trigger(path.name, t, has_wake_word(text), text))
        quiet_until = t + REFRACTORY_S
        engine.reset()
    return triggers, len(audio) / SAMPLE_RATE - tail_s


def tag_of(name: str) -> str:
    parts = Path(name).stem.split("_")
    return parts[1] if len(parts) >= 3 else "?"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--informe", type=Path, help="guardar el informe en Markdown")
    parser.add_argument("--carpeta", type=Path, default=RECORDINGS)
    args = parser.parse_args()

    settings = load_settings()
    engine = VoskWakeWord(MODELS["wake"].path(), settings.wake.word)
    stt = WhisperServer(
        whisper_server_path(settings),
        settings.stt.model,
        language=settings.stt.language,
        gpu=settings.stt.gpu,
    )
    await stt.start()
    results: dict[str, Summary] = defaultdict(Summary)
    per_tag: dict[str, list[bool]] = defaultdict(list)
    t0 = time.perf_counter()
    try:
        for mode in ("positivos", "parecidas", "continuo"):
            for path in sorted((args.carpeta / mode).glob("*.wav")):
                triggers, seconds = await scan(path, engine, stt)
                results[mode].seconds += seconds
                results[mode].triggers += triggers
                if mode == "positivos":
                    per_tag[tag_of(path.name)].append(any(t.verified for t in triggers))
    finally:
        await stt.stop()

    lines = [f"# Activación · {datetime.now():%Y-%m-%d %H:%M}", ""]
    lines.append(f"Detector: Vosk («{settings.wake.word}») + verificación con whisper.")
    lines.append("")
    if per_tag:
        hits = sum(sum(v) for v in per_tag.values())
        total = sum(len(v) for v in per_tag.values())
        lines += [
            f"**Aciertos con «Nyx»: {hits}/{total} ({100 * hits / total:.0f} %)** "
            "(objetivo: más del 95 %).",
            "",
            "| Tipo | Aciertos |",
            "| --- | --- |",
        ]
        lines += [f"| {tag} | {sum(v)}/{len(v)} |" for tag, v in sorted(per_tag.items())]
        lines.append("")
    for mode, title in (("parecidas", "Palabras parecidas"), ("continuo", "Uso normal")):
        summary = results.get(mode)
        if summary is None or not summary.seconds:
            continue
        false = [t for t in summary.triggers if t.verified]
        raw = len(summary.triggers)
        hours = summary.seconds / 3600
        lines.append(
            f"**{title}:** {summary.seconds / 60:.0f} min, {raw} saltos del detector, "
            f"**{len(false)} activaciones falsas** tras whisper"
            + (
                f" ({len(false) / hours:.2f} por hora; objetivo: < 0,125)"
                if mode == "continuo"
                else ""
            )
            + "."
        )
        lines += [f"- {t.file} @ {t.at_s:.1f} s → «{t.heard}»" for t in false]
        lines.append("")
    lines.append(f"Tiempo de evaluación: {time.perf_counter() - t0:.0f} s.")
    text = "\n".join(lines) + "\n"
    print(text)
    if not per_tag and not results:
        print(f"No hay grabaciones en {args.carpeta}: usa scripts/record_samples.py")
    if args.informe:
        args.informe.parent.mkdir(parents=True, exist_ok=True)
        args.informe.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
