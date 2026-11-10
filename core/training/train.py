r"""Entrena el detector de «Nyx» sobre los rasgos de build.py (fase 4b). CPU, sin CUDA.

Red pequeña encima del modelo base de Google: (16, 96) → probabilidad de que acabe de oírse
«Nyx». Las falsas activaciones pesan más que los fallos (`--peso-negativos`): whisper ya
filtra después, pero cada activación falsa enciende el micro y se nota.

    uv run python training/train.py
Sale %LOCALAPPDATA%\Nyx\training\modelos\nyx.onnx (+ métricas en nyx.json).
"""

from __future__ import annotations

import argparse
import json
import sys
import time

import numpy as np
import torch
from torch import nn

from nyx.paths import local_dir
from nyx.wake.features import EMB_DIM, N_EMB

DATA = local_dir() / "training" / "conjunto"
OUT = local_dir() / "training" / "modelos"


class Detector(nn.Module):
    def __init__(self, hidden: int = 128) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Flatten(),
            nn.Linear(N_EMB * EMB_DIM, hidden),
            nn.LayerNorm(hidden),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden, hidden),
            nn.LayerNorm(hidden),
            nn.ReLU(),
            nn.Linear(hidden, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out: torch.Tensor = self.net(x)
        return out.squeeze(-1)


class Exported(nn.Module):
    """Lo que va en el ONNX: probabilidad (0–1) en vez de logit."""

    def __init__(self, model: Detector) -> None:
        super().__init__()
        self.model = model

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return torch.sigmoid(self.model(x))


def load(name: str) -> tuple[torch.Tensor, torch.Tensor]:
    data = np.load(DATA / name)
    return torch.from_numpy(data["X"].astype(np.float32)), torch.from_numpy(
        data["y"].astype(np.float32)
    )


def metrics(model: nn.Module, xs: torch.Tensor, y: torch.Tensor) -> dict[str, float]:
    model.eval()
    with torch.no_grad():
        p = torch.sigmoid(torch.cat([model(xs[i : i + 4096]) for i in range(0, len(xs), 4096)]))
    out: dict[str, float] = {}
    for t in (0.3, 0.5, 0.7, 0.9):
        hit = ((p >= t) & (y == 1)).sum().item() / max(1, int((y == 1).sum()))
        false = ((p >= t) & (y == 0)).sum().item() / max(1, int((y == 0).sum()))
        out[f"aciertos@{t}"] = round(hit, 4)
        out[f"falsos@{t}"] = round(false, 5)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epocas", type=int, default=40)
    parser.add_argument("--lote", type=int, default=512)
    parser.add_argument("--peso-negativos", type=float, default=3.0)
    parser.add_argument("--semilla", type=int, default=3)
    args = parser.parse_args()

    torch.manual_seed(args.semilla)
    torch.set_num_threads(max(1, (torch.get_num_threads() or 2) - 1))
    xtr, ytr = load("train.npz")
    xva, yva = load("val.npz")
    print(f"Entrenamiento: {len(ytr)} ({int(ytr.sum())} +); validación: {len(yva)}", flush=True)
    model = Detector()
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-3)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epocas)
    loss_fn = nn.BCEWithLogitsLoss(reduction="none")
    t0 = time.perf_counter()
    for epoch in range(1, args.epocas + 1):
        model.train()
        order = torch.randperm(len(ytr))
        total = 0.0
        for i in range(0, len(order), args.lote):
            idx = order[i : i + args.lote]
            x, y = xtr[idx], ytr[idx]
            # Un poco de ruido en los rasgos: generaliza mejor a micros que no ha oído.
            x = x + 0.05 * torch.randn_like(x)
            weight = torch.where(y == 0, args.peso_negativos, 1.0)
            loss = (loss_fn(model(x), y) * weight).mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
            total += loss.item() * len(idx)
        sched.step()
        if epoch % 5 == 0 or epoch == args.epocas:
            m = metrics(model, xva, yva)
            print(
                f"época {epoch:3d}  pérdida {total / len(ytr):.4f}  "
                f"aciertos@0.5 {m['aciertos@0.5']:.3f}  falsos@0.5 {m['falsos@0.5']:.4f}",
                flush=True,
            )
    final = metrics(model, xva, yva)
    OUT.mkdir(parents=True, exist_ok=True)
    model.eval()
    torch.onnx.export(
        Exported(model),
        (torch.zeros(1, N_EMB, EMB_DIM),),
        str(OUT / "nyx.onnx"),
        input_names=["x"],
        output_names=["p"],
        dynamic_axes={"x": {0: "n"}, "p": {0: "n"}},
        dynamo=False,
    )
    info = {"validacion": final, "segundos": round(time.perf_counter() - t0), **vars(args)}
    (OUT / "nyx.json").write_text(json.dumps(info, indent=2, ensure_ascii=False), "utf-8")
    print(json.dumps(final, indent=2), f"\nModelo: {OUT / 'nyx.onnx'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
