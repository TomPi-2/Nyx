r"""Monta el conjunto de entrenamiento de «Nyx» (fase 4b): ventanas de 2 s → rasgos (16, 96).

Positivos: cada «Nyx» sintético acaba entre 0,05 y 0,35 s antes del final de la ventana (el
detector decide justo cuando termina la palabra), con reverberación, ruido o habla de fondo y
volumen al azar. Negativos: trozos de habla real en español (OpenSLR), ruidos, y las palabras
parecidas sintéticas colocadas igual que los positivos.

Las grabaciones del usuario NO se usan aquí: sirven para evaluar sin trampas.

    uv run python training/build.py
"""

from __future__ import annotations

import argparse
import random
import sys
import wave
import zlib
from pathlib import Path

import numpy as np
import numpy.typing as npt
from scipy.signal import fftconvolve

sys.path.insert(0, str(Path(__file__).resolve().parent))

from datasets import data_dir

from nyx.paths import local_dir
from nyx.wake.features import FeatureExtractor

RATE = 16_000
WINDOW = 32_000  # 2 s → 16 vectores
OUT = local_dir() / "training" / "conjunto"
SYNTH = local_dir() / "training" / "sinteticos"

Audio = npt.NDArray[np.float32]


def read(path: Path) -> Audio:
    with wave.open(str(path), "rb") as w:
        if w.getframerate() != RATE or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise ValueError(f"{path.name}: hace falta WAV 16 kHz mono 16 bits")
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return np.asarray(pcm, dtype=np.float32) / np.float32(32768)


def read_any(path: Path) -> Audio | None:
    """Los WAV de OpenSLR 61/71/72 van a 48 kHz y los de RIRS a 16 kHz: se adaptan."""
    from scipy.signal import resample_poly

    try:
        with wave.open(str(path), "rb") as w:
            rate, channels, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
            raw = w.readframes(w.getnframes())
    except wave.Error, EOFError:
        return None
    if width != 2:
        return None
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768
    if channels > 1:
        audio = audio.reshape(-1, channels)[:, 0]
    if rate != RATE:
        audio = resample_poly(audio, RATE, rate).astype(np.float32)
    return np.asarray(audio, dtype=np.float32)


def trim(audio: Audio, threshold: float = 0.02) -> Audio:
    """Quita el silencio de los extremos (para saber dónde acaba la palabra)."""
    loud = np.flatnonzero(np.abs(audio) > threshold * (np.max(np.abs(audio)) or 1))
    return audio[loud[0] : loud[-1] + 1] if len(loud) else audio


class Augmenter:
    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        root = data_dir() / "rirs" / "RIRS_NOISES"
        self.rirs = sorted((root / "simulated_rirs").rglob("*.wav"))
        self.rirs += sorted((root / "real_rirs_isotropic_noises").glob("*rir*.wav"))
        self.noises = sorted((root / "pointsource_noises").glob("*.wav"))
        self.noises += sorted((root / "real_rirs_isotropic_noises").glob("*noise*.wav"))
        self.speech = sorted(
            p for key in ("slr61", "slr71", "slr72") for p in (data_dir() / key).rglob("*.wav")
        )
        print(
            f"Reverberaciones: {len(self.rirs)}, ruidos: {len(self.noises)}, "
            f"habla: {len(self.speech)}",
            flush=True,
        )

    def crop(self, path: Path, length: int) -> Audio:
        audio = read_any(path)
        if audio is None or len(audio) == 0:
            return np.zeros(length, dtype=np.float32)
        if len(audio) < length:
            audio = np.tile(audio, length // len(audio) + 1)
        start = self.rng.randrange(len(audio) - length + 1)
        return audio[start : start + length]

    def reverb(self, audio: Audio) -> Audio:
        if not self.rirs or self.rng.random() > 0.45:
            return audio
        rir = read_any(self.rng.choice(self.rirs))
        if rir is None or len(rir) == 0:
            return audio
        rir = rir / (np.max(np.abs(rir)) or 1)
        out = fftconvolve(audio, rir)[: len(audio)]
        scaled = out / (np.max(np.abs(out)) or 1) * np.max(np.abs(audio))
        return np.asarray(scaled, dtype=np.float32)

    def background(self) -> Audio:
        """Fondo de 2 s: ruido, habla lejana, ambos o casi silencio."""
        choice = self.rng.random()
        out = np.zeros(WINDOW, dtype=np.float32)
        if choice < 0.35 and self.noises:
            out += self.crop(self.rng.choice(self.noises), WINDOW)
        elif choice < 0.7 and self.speech:
            out += self.crop(self.rng.choice(self.speech), WINDOW)
        elif choice < 0.85 and self.noises and self.speech:
            out += self.crop(self.rng.choice(self.noises), WINDOW)
            out += self.crop(self.rng.choice(self.speech), WINDOW)
        out += (
            np.random.default_rng(self.rng.randrange(1 << 30))
            .normal(0, self.rng.uniform(1e-4, 3e-3), WINDOW)
            .astype(np.float32)
        )
        return out

    def place(self, word: Audio) -> Audio:
        """La palabra acaba entre 0,05 y 0,35 s antes del final, sobre un fondo a SNR al azar."""
        word = self.reverb(trim(word))
        word = word[-(WINDOW - 800) :]
        end = WINDOW - int(self.rng.uniform(0.05, 0.35) * RATE)
        start = max(0, end - len(word))
        out = np.zeros(WINDOW, dtype=np.float32)
        out[start : start + len(word)] = word[: WINDOW - start]
        bg = self.background()
        snr_db = self.rng.uniform(0, 30)
        p_word = float(np.mean(word**2)) or 1e-8
        p_bg = float(np.mean(bg**2)) or 1e-8
        out += bg * np.sqrt(p_word / (p_bg * 10 ** (snr_db / 10)))
        return self.level(out)

    def level(self, audio: Audio) -> Audio:
        peak = float(np.max(np.abs(audio))) or 1.0
        return (audio / peak * self.rng.uniform(0.05, 0.9)).astype(np.float32)


def to_pcm(audio: Audio) -> npt.NDArray[np.int16]:
    return np.clip(audio * 32767, -32768, 32767).astype(np.int16)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--copias", type=int, default=3, help="versiones de cada positivo")
    parser.add_argument("--habla", type=int, default=16000, help="ventanas de habla negativa")
    parser.add_argument("--ruido", type=int, default=3000, help="ventanas solo de ruido")
    parser.add_argument("--semilla", type=int, default=11)
    args = parser.parse_args()

    rng = random.Random(args.semilla)
    aug = Augmenter(rng)
    oww = data_dir() / "oww"
    fx = FeatureExtractor(oww / "melspectrogram.onnx", oww / "embedding_model.onnx", threads=4)
    positives = sorted((SYNTH / "positivos").glob("*.wav"))
    negatives = sorted((SYNTH / "negativos").glob("*.wav"))
    if not positives or not aug.speech:
        print("Faltan muestras: training/generate.py, filter.py y download.py")
        return 1

    feats_all: list[npt.NDArray[np.float16]] = []
    y: list[int] = []
    group: list[int] = []  # para separar entrenamiento y validación sin mezclar orígenes

    def add(audio: Audio, label: int, origin: int) -> None:
        feats = fx.clip(to_pcm(audio))
        if feats.shape[0] == 16:
            feats_all.append(feats.astype(np.float16))
            y.append(label)
            group.append(origin)

    for i, path in enumerate(positives):
        word = read(path)
        for _ in range(args.copias):
            add(aug.place(word), 1, i)
        if (i + 1) % 1000 == 0:
            print(f"  positivos: {i + 1}/{len(positives)}", flush=True)
    base = len(positives)
    for i, path in enumerate(negatives):
        word = read(path)
        for _ in range(2):
            add(aug.place(word), 0, base + i)
    base += len(negatives)
    print(f"  palabras parecidas: {len(negatives)}", flush=True)
    for i in range(args.habla):
        path = rng.choice(aug.speech)
        audio = aug.reverb(aug.crop(path, WINDOW))
        add(
            aug.level(audio + 0.3 * aug.background()),
            0,
            base + zlib.crc32(path.name.encode()) % 100_000,
        )
        if (i + 1) % 4000 == 0:
            print(f"  habla: {i + 1}/{args.habla}", flush=True)
    base += 100_000
    for i in range(args.ruido):
        add(aug.level(aug.background()), 0, base + i)
    print(f"  ruido: {args.ruido}", flush=True)

    xa = np.stack(feats_all)
    ya = np.asarray(y, dtype=np.uint8)
    ga = np.asarray(group)
    val = (ga * 2654435761 % 10) == 0  # ~10 % de los orígenes, siempre los mismos
    OUT.mkdir(parents=True, exist_ok=True)
    np.savez(OUT / "train.npz", X=xa[~val], y=ya[~val])
    np.savez(OUT / "val.npz", X=xa[val], y=ya[val])
    print(
        f"Listo: {len(ya)} ventanas ({int(ya.sum())} positivas); "
        f"validación {int(val.sum())}. En {OUT}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
