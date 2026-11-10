r"""Filtro de calidad de las muestras sintéticas con whisper (fase 4b).

Un positivo que whisper no oye como «Nyx» (voz rara, palabra cortada) o un negativo que sí
lo parece se mueve a sinteticos\descartados\: entrenar con etiquetas falsas empeora el modelo.

    uv run python training/filter.py
"""

from __future__ import annotations

import asyncio
import shutil
import sys
import wave
from pathlib import Path

import numpy as np

from nyx.paths import local_dir
from nyx.pipeline import STT_PROMPT
from nyx.services import whisper_server_path
from nyx.settings.model import load_settings
from nyx.stt.normalize import has_wake_word
from nyx.stt.whisper_server import WhisperServer

BASE = local_dir() / "training" / "sinteticos"
PAD = np.zeros(4000, dtype=np.int16)  # 0,25 s de silencio a cada lado, como en la vida real


def read(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)


async def main() -> int:
    settings = load_settings()
    stt = WhisperServer(
        whisper_server_path(settings),
        settings.stt.model,
        language=settings.stt.language,
        gpu=settings.stt.gpu,
    )
    await stt.start()
    rejected = BASE / "descartados"
    try:
        for kind, want in (("positivos", True), ("negativos", False)):
            (rejected / kind).mkdir(parents=True, exist_ok=True)
            files = sorted((BASE / kind).glob("*.wav"))
            dropped = 0
            for i, path in enumerate(files, 1):
                text = await stt.transcribe(np.concatenate([PAD, read(path), PAD]), STT_PROMPT)
                if has_wake_word(text) != want:
                    shutil.move(path, rejected / kind / path.name)
                    dropped += 1
                if i % 500 == 0:
                    print(f"  {kind}: {i}/{len(files)} ({dropped} descartados)", flush=True)
            print(f"{kind}: {len(files) - dropped} buenos, {dropped} descartados", flush=True)
    finally:
        await stt.stop()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
