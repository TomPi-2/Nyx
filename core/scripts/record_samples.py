r"""Graba muestras para medir (y luego entrenar) la palabra de activación (fase 4a).

Todo se guarda solo en este equipo: %LOCALAPPDATA%\Nyx\training\grabaciones\<modo>\.
Usa el micrófono de los ajustes de Nyx (se puede grabar con Nyx abierto).

    uv run python scripts/record_samples.py positivos    # ~50 veces «Nyx» (unos 5 min)
    uv run python scripts/record_samples.py parecidas    # palabras que se parecen (~3 min)
    uv run python scripts/record_samples.py continuo     # uso normal, hasta Ctrl+C

En «positivos» y «parecidas»: pulsa Enter, espera a «¡Ahora!» y habla. «r» + Enter repite la
última; «q» + Enter sale (lo grabado se queda).
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import sys
import wave
from collections import deque
from datetime import datetime
from pathlib import Path

import numpy as np

from nyx.audio.capture import FRAME_S, SAMPLE_RATE, AudioCapture, Frame
from nyx.paths import local_dir
from nyx.settings.model import load_settings

LEAD_S = 0.25  # se guarda un poco de antes de «¡Ahora!» por si se adelanta
CHUNK_MIN = 5  # «continuo»: un archivo cada 5 minutos

# (etiqueta, instrucción, veces, segundos)
POSITIVE_ROUNDS = [
    ("cerca", "Di «Nyx» normal, a tu distancia de siempre", 10, 2.0),
    ("lejos", "Aléjate 1–2 m del micro (o gira la cabeza) y di «Nyx»", 10, 2.0),
    ("bajito", "Di «Nyx» en voz baja", 8, 2.0),
    ("alto", "Di «Nyx» más alto o con prisa", 6, 2.0),
    ("relajado", "Di «Nyx» como de pasada, sin vocalizar mucho", 6, 2.0),
    ("frase", "Di «Nyx» y una orden seguida (p. ej. «Nyx, abre Spotify»)", 10, 3.5),
]
LOOKALIKES = [
    "nix", "nicks", "mix", "six", "fix", "Félix", "ni", "nis", "Nike", "next", "ni se",
    "y ya", "nexo", "nicho", "Linux", "max", "nos", "nieve", "mis", "Niki", "Nico",
    "ni idea", "ninguno", "ni hablar", "lince", "Unix", "taxis", "explica",
]  # fmt: skip


def out_dir(mode: str) -> Path:
    path = local_dir() / "training" / "grabaciones" / mode
    path.mkdir(parents=True, exist_ok=True)
    return path


def save(path: Path, frames: list[Frame]) -> None:
    audio = np.concatenate(frames) if frames else np.zeros(0, dtype=np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(audio.astype(np.int16).tobytes())


class Recorder:
    """Lee el micro en segundo plano y guarda los últimos segundos (y todo, si se pide)."""

    def __init__(self, device: str | None, keep_s: float = 8.0) -> None:
        self.capture = AudioCapture(device)
        self.recent: deque[Frame] = deque(maxlen=int(keep_s / FRAME_S) + 1)
        self.sink: list[Frame] | None = None
        self._task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> Recorder:
        self.capture.start()
        self._task = asyncio.create_task(self._read())
        await asyncio.sleep(0.3)
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        self.capture.stop()

    async def _read(self) -> None:
        async for frame in self.capture.frames():
            self.recent.append(frame)
            if self.sink is not None:
                self.sink.append(frame)

    async def clip(self, seconds: float) -> list[Frame]:
        print("   ¡Ahora!", flush=True)
        await asyncio.sleep(seconds)
        n = int((seconds + LEAD_S) / FRAME_S)
        return list(self.recent)[-n:]


async def ask(prompt: str) -> str:
    return (await asyncio.to_thread(input, prompt)).strip().lower()


async def guided(rec: Recorder, mode: str, items: list[tuple[str, str, float]]) -> int:
    folder = out_dir(mode)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    saved = 0
    i = 0
    while i < len(items):
        tag, instruction, seconds = items[i]
        answer = await ask(f"[{i + 1}/{len(items)}] {instruction}  (Enter)  ")
        if answer == "q":
            break
        if answer == "r" and i > 0:
            i -= 1
            tag, instruction, seconds = items[i]
            print(f"   Repetimos: {instruction}")
        frames = await rec.clip(seconds)
        save(folder / f"{stamp}_{tag}_{i:03d}.wav", frames)
        saved += 1
        i += 1
    print(f"Guardadas {saved} muestras en {folder}")
    return saved


async def continuous(rec: Recorder) -> None:
    folder = out_dir("continuo")
    print(f"Grabando el micro en trozos de {CHUNK_MIN} min en {folder}. Ctrl+C para parar.")
    total = 0.0
    try:
        while True:
            rec.sink = []
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            await asyncio.sleep(CHUNK_MIN * 60)
            chunk, rec.sink = rec.sink, None
            save(folder / f"{stamp}.wav", chunk)
            total += len(chunk) * FRAME_S
            print(f"  {total / 60:.0f} min grabados")
    except (asyncio.CancelledError, KeyboardInterrupt):
        if rec.sink:
            save(folder / f"{datetime.now():%Y%m%d-%H%M%S}.wav", rec.sink)
            total += len(rec.sink) * FRAME_S
        print(f"\nParado. {total / 60:.1f} min en total.")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("modo", choices=["positivos", "parecidas", "continuo"])
    args = parser.parse_args()
    settings = load_settings()
    async with Recorder(settings.audio.input_device) as rec:
        if args.modo == "positivos":
            items = [(t, ins, s) for t, ins, n, s in POSITIVE_ROUNDS for _ in range(n)]
            await guided(rec, "positivos", items)
        elif args.modo == "parecidas":
            items = [(w.replace(" ", "-"), f"Di «{w}»", 2.0) for w in LOOKALIKES]
            await guided(rec, "parecidas", items)
        else:
            await continuous(rec)
    return 0


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        sys.exit(asyncio.run(main()))
