r"""Calibración del detector con las muestras del usuario (SPEC sección 4.3, fase 4d).

Ajusta el modelo base a la voz y al micro del usuario con sus grabaciones de
record_samples.py (sin descargas): sus «Nyx» sobre fondos de su propio uso normal, y como
negativos su uso normal y sus palabras parecidas. Para no olvidar lo general, el ajuste se
penaliza si se aleja del modelo base (L2-SP) y dura pocas épocas.

El resultado va a %LOCALAPPDATA%\Nyx\models\nyx-personal.onnx; si existe, Nyx lo usa.
Importa PyTorch: solo se usa al calibrar.
"""

from __future__ import annotations

import random
import wave
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
import torch
from torch import nn

from nyx.paths import models_dir
from nyx.wake.features import N_EMB, FeatureExtractor
from nyx.wake.net import BASE_WEIGHTS, Detector

PERSONAL_MODEL = models_dir() / "nyx-personal.onnx"
RATE = 16_000
WINDOW = 32_000  # 2 s → 16 vectores
SOUNDS_THE_SAME = {"nix", "nicks"}  # homófonos de «Nyx»: ni positivos ni negativos
REFRACTORY = 12  # vectores (~1 s) tras una activación

Audio = npt.NDArray[np.float32]
Feats = npt.NDArray[np.float32]


@dataclass
class Recordings:
    positives: list[Path]
    lookalikes: list[Path]
    ambient: list[Path]  # uso normal (modo «continuo»)

    @classmethod
    def load(cls, folder: Path) -> Recordings:
        def wavs(mode: str) -> list[Path]:
            return sorted((folder / mode).glob("*.wav"))

        lookalikes = [p for p in wavs("parecidas") if tag_of(p) not in SOUNDS_THE_SAME]
        return cls(wavs("positivos"), lookalikes, wavs("continuo"))


def tag_of(path: Path) -> str:
    parts = path.stem.split("_")
    return parts[1] if len(parts) >= 3 else "?"


def read(path: Path) -> Audio:
    with wave.open(str(path), "rb") as w:
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return np.asarray(pcm, dtype=np.float32) / np.float32(32768)


def to_pcm(audio: Audio) -> npt.NDArray[np.int16]:
    return np.asarray(np.clip(audio * 32767, -32768, 32767), dtype=np.int16)


def trim(audio: Audio, threshold: float = 0.08) -> Audio:
    loud = np.flatnonzero(np.abs(audio) > threshold * (float(np.max(np.abs(audio))) or 1.0))
    return audio[max(0, loud[0] - 800) : loud[-1] + 800] if len(loud) else audio


class Builder:
    """Ventanas de 2 s con la palabra al final sobre fondos del propio usuario."""

    def __init__(self, fx: FeatureExtractor, ambient: Sequence[Path], rng: random.Random) -> None:
        self.fx = fx
        self.rng = rng
        self.ambient = [read(p) for p in ambient]
        self.ambient = [a for a in self.ambient if len(a) > WINDOW]

    def background(self) -> Audio:
        if not self.ambient or self.rng.random() < 0.2:
            return np.zeros(WINDOW, dtype=np.float32)
        audio = self.rng.choice(self.ambient)
        start = self.rng.randrange(len(audio) - WINDOW)
        return audio[start : start + WINDOW].copy()

    def place(self, word: Audio) -> Audio:
        word = trim(word)[-(WINDOW - 800) :]
        end = WINDOW - int(self.rng.uniform(0.05, 0.35) * RATE)
        start = max(0, end - len(word))
        out = self.background() * self.rng.uniform(0.1, 1.0)
        out[start : start + len(word)] += word[: WINDOW - start] * self.rng.uniform(0.4, 2.0)
        return np.asarray(np.clip(out, -1, 1), dtype=np.float32)

    def features(self, audio: Audio) -> Feats | None:
        feats = self.fx.clip(to_pcm(audio))
        return feats if feats.shape[0] == N_EMB else None

    def dataset(
        self, positives: Sequence[Path], lookalikes: Sequence[Path], copies: int = 20
    ) -> tuple[Feats, Feats]:
        pos: list[Feats] = []
        neg: list[Feats] = []
        for path in positives:
            word = read(path)
            for _ in range(copies):
                if (f := self.features(self.place(word))) is not None:
                    pos.append(f)
        for path in lookalikes:
            word = read(path)
            for _ in range(copies // 2):
                if (f := self.features(self.place(word))) is not None:
                    neg.append(f)
        for _ in range(max(len(pos), 1000)):
            if (f := self.features(self.background())) is not None:
                neg.append(f)
        return np.stack(pos), np.stack(neg)


def load_base() -> Detector:
    model = Detector()
    model.load_state_dict(torch.load(BASE_WEIGHTS, weights_only=True))
    model.eval()  # sin dropout: si no, las medidas salen con ruido aleatorio
    return model


def finetune(
    pos: Feats,
    neg: Feats,
    *,
    epochs: int = 12,
    lr: float = 3e-4,
    anchor: float = 0.05,
    seed: int = 5,
) -> Detector:
    torch.manual_seed(seed)
    model = load_base()
    start = {k: v.detach().clone() for k, v in model.named_parameters()}
    x = torch.from_numpy(np.concatenate([pos, neg]).astype(np.float32))
    y = torch.cat([torch.ones(len(pos)), torch.zeros(len(neg))])
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.BCEWithLogitsLoss(reduction="none")
    for _ in range(epochs):
        model.train()
        order = torch.randperm(len(y))
        for i in range(0, len(order), 256):
            idx = order[i : i + 256]
            batch = x[idx] + 0.1 * torch.randn_like(x[idx])
            weight = torch.where(y[idx] == 0, 3.0, 1.0)
            loss = (loss_fn(model(batch), y[idx]) * weight).mean()
            # L2-SP: no alejarse del modelo base (no olvidar lo general).
            loss = loss + anchor * sum(
                ((p - start[n]) ** 2).sum() for n, p in model.named_parameters()
            )
            opt.zero_grad()
            loss.backward()
            opt.step()
    model.eval()
    return model


def probabilities(model: Detector, feats: Feats) -> npt.NDArray[np.float32]:
    """Probabilidad de cada ventana de 16 vectores consecutivos de una secuencia."""
    if len(feats) < N_EMB:
        return np.zeros(0, dtype=np.float32)
    windows = np.stack([feats[i : i + N_EMB] for i in range(len(feats) - N_EMB + 1)])
    with torch.no_grad():
        p = torch.sigmoid(model(torch.from_numpy(windows.astype(np.float32))))
    return np.asarray(p.numpy(), dtype=np.float32)


@dataclass
class Score:
    hits: int
    total: int
    false_triggers: int
    hours: float

    @property
    def recall(self) -> float:
        return self.hits / max(1, self.total)

    @property
    def false_per_hour(self) -> float:
        return self.false_triggers / max(1e-9, self.hours)


def evaluate(
    model: Detector,
    fx: FeatureExtractor,
    positives: Sequence[Path],
    ambient: Sequence[Path],
    threshold: float = 0.5,
) -> Score:
    """Solo el detector (sin whisper): aciertos con 2 s de silencio delante, como en Nyx, y
    saltos por hora en el uso normal (con 1 s de espera tras cada uno)."""
    lead = np.zeros(WINDOW, dtype=np.float32)
    tail = np.zeros(RATE // 2, dtype=np.float32)
    hits = 0
    for path in positives:
        feats = fx.clip(to_pcm(np.concatenate([lead, read(path), tail])))
        hits += bool((probabilities(model, feats) >= threshold).any())
    false_triggers = 0
    seconds = 0.0
    for path in ambient:
        audio = read(path)
        seconds += len(audio) / RATE
        p = probabilities(model, fx.clip(to_pcm(audio)))
        i = 0
        while i < len(p):
            if p[i] >= threshold:
                false_triggers += 1
                i += REFRACTORY
            else:
                i += 1
    return Score(hits, len(positives), false_triggers, seconds / 3600)
