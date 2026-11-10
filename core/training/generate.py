r"""Muestras sintéticas para entrenar «Nyx» (fase 4b) con las voces libres de datasets.py.

- positivos: «Nyx», «Nix», «Niks»… con voz, hablante, velocidad y entonación al azar.
- negativos: palabras y frases que se parecen pero no son «Nyx» («Nick», «next», «Félix»…).

Salen WAV de 16 kHz en %LOCALAPPDATA%\Nyx\training\sinteticos\{positivos,negativos}\.

    uv run python training/generate.py                 # 4000 positivos y 4000 negativos
    uv run python training/generate.py --positivos 200 --negativos 200   # prueba rápida
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
from scipy.signal import resample_poly

sys.path.insert(0, str(Path(__file__).resolve().parent))

from datasets import SOURCES, data_dir

from nyx.paths import local_dir

RATE = 16_000
# «Nyx» se pronuncia /niks/: en español «Nyx», «Nix», «Niks»; la voz inglesa lo dice igual.
POSITIVE = {
    "es": ["Nyx.", "Nix.", "Niks.", "Nics.", "Nicks."],
    "en": ["Nix.", "Nicks.", "Nyx.", "Nix!", "Nix?"],
}
# Parecidas pero distintas (sin homófonos: «nix», «nicks», «Knicks» suenan igual que «Nyx»).
NEGATIVE = {
    "es": [
        "ni", "nis", "mix", "six", "fix", "Félix", "Nike", "next", "ni se", "y ya", "nexo",
        "nicho", "Linux", "max", "nos", "nieve", "mis", "Niki", "Nico", "ni idea", "ninguno",
        "ni hablar", "lince", "Unix", "taxis", "explica", "texto", "éxito", "anexo", "mixto",
        "nicotina", "Nicolás", "es mi", "que sí", "dime", "vale", "venga", "nada", "noche",
        "nueve", "lista", "pista", "fíjate", "mira esto", "un momento", "a ver", "oye",
    ],
    "en": [
        "nick", "next", "mix", "six", "fix", "kicks", "necks", "nice", "knees", "nicky",
        "sticks", "picks", "ticks", "nexus", "annex", "nine", "yes", "no", "hey", "okay",
    ],
}  # fmt: skip


WEAK_VOICES = {"piper-carlfm", "piper-ald"}


@dataclass
class Voice:
    key: str
    language: str
    model: Any
    speakers: int
    rate: int


def load_voices() -> list[Voice]:
    from piper import PiperVoice

    voices = []
    for source in SOURCES:
        if source.use != "positivos" or not source.filename.endswith(".onnx"):
            continue
        model_path = source.path()
        config_path = model_path.with_suffix(".onnx.json")
        config = json.loads(config_path.read_text(encoding="utf-8"))
        voices.append(
            Voice(
                source.key,
                "en" if "en_US" in source.filename else "es",
                PiperVoice.load(model_path, config_path=config_path),
                int(config.get("num_speakers", 1)),
                int(config["audio"]["sample_rate"]),
            )
        )
    return voices


def synth(voice: Voice, text: str, rng: random.Random) -> npt.NDArray[np.int16]:
    from piper import SynthesisConfig

    cfg = SynthesisConfig(
        speaker_id=rng.randrange(voice.speakers) if voice.speakers > 1 else None,
        length_scale=rng.uniform(0.75, 1.4),  # velocidad
        noise_scale=rng.uniform(0.4, 1.0),  # variación de la voz
        noise_w_scale=rng.uniform(0.5, 1.2),  # variación del ritmo
    )
    chunks = list(voice.model.synthesize(text, syn_config=cfg))
    audio = np.concatenate([c.audio_float_array for c in chunks]) if chunks else np.zeros(1)
    audio = resample_poly(audio, RATE, voice.rate)  # 22 050 → 16 000 Hz
    peak = float(np.max(np.abs(audio))) or 1.0
    audio = audio / peak * rng.uniform(0.3, 0.95)
    return np.asarray(audio * 32767, dtype=np.int16)


def save(path: Path, audio: npt.NDArray[np.int16]) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(audio.tobytes())


def generate(kind: str, count: int, voices: list[Voice], rng: random.Random) -> None:
    folder = local_dir() / "training" / "sinteticos" / kind
    folder.mkdir(parents=True, exist_ok=True)
    texts = POSITIVE if kind == "positivos" else NEGATIVE
    # La voz inglesa tiene 904 hablantes: la mitad de las muestras, para variar acentos.
    english = [v for v in voices if v.language == "en"]
    spanish = [v for v in voices if v.language == "es"]
    if kind == "positivos":  # estas dos dicen mal las palabras sueltas: solo para negativos
        spanish = [v for v in spanish if v.key not in WEAK_VOICES]
    for i in range(count):
        pool = english if english and i % 2 else spanish
        voice = rng.choice(pool)
        text = rng.choice(texts[voice.language])
        save(folder / f"{voice.key}_{i:05d}.wav", synth(voice, text, rng))
        if (i + 1) % 500 == 0:
            print(f"  {kind}: {i + 1}/{count}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positivos", type=int, default=4000)
    parser.add_argument("--negativos", type=int, default=4000)
    parser.add_argument("--semilla", type=int, default=7)
    args = parser.parse_args()
    missing = [s.filename for s in SOURCES if s.use == "positivos" and not s.path().exists()]
    if missing:
        print(f"Faltan voces en {data_dir()}: ejecuta training/download.py ({missing})")
        return 1
    rng = random.Random(args.semilla)
    voices = load_voices()
    print(f"Voces: {', '.join(f'{v.key} ({v.speakers})' for v in voices)}")
    generate("positivos", args.positivos, voices, rng)
    generate("negativos", args.negativos, voices, rng)
    print("Listo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
