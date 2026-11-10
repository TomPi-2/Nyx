"""La red del detector de «Nyx» (PyTorch). La usan el entrenamiento (training/train.py) y la
calibración con las muestras del usuario (calibrate.py). En Nyx corre como ONNX.

Importar este módulo carga PyTorch: solo se hace al entrenar o calibrar.
"""

from __future__ import annotations

from pathlib import Path

import torch
from torch import nn

from nyx.wake.features import EMB_DIM, N_EMB

# Pesos del modelo base (los mismos que nyx-v1.onnx), para calibrar a partir de ellos.
BASE_WEIGHTS = Path(__file__).resolve().parent / "data" / "nyx-v1.pt"


class Detector(nn.Module):
    """(n, 16, 96) → logit de «acaba de oírse Nyx»."""

    def __init__(self, hidden: int = 128) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Flatten(),
            nn.Linear(N_EMB * EMB_DIM, hidden),
            nn.LayerNorm(hidden),
            nn.ReLU(),
            nn.Dropout(0.3),
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


def export_onnx(model: Detector, path: Path) -> None:
    """Exporta a ONNX (entrada «x» (n, 16, 96), salida «p»). Necesita el paquete onnx."""
    model.eval()
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        Exported(model),
        (torch.zeros(1, N_EMB, EMB_DIM),),
        str(path),
        input_names=["x"],
        output_names=["p"],
        dynamic_axes={"x": {0: "n"}, "p": {0: "n"}},
        dynamo=False,
    )
