r"""Calibra «Nyx» con tus grabaciones (fase 4d). En la fase 5 lo hará el asistente de inicio.

1. Mide de forma honesta: ajusta con la mitad de tus «Nyx» (y de tu uso normal) y mide con
   la otra mitad, y al revés. Compara con el modelo base.
2. Si mejora, ajusta con todo y guarda %LOCALAPPDATA%\Nyx\models\nyx-personal.onnx, que Nyx
   usa en vez del base (bandeja → Reiniciar núcleo). Para volver al base, bórralo.

    uv run python scripts/calibrate.py
    uv run python scripts/calibrate.py --solo-medir
"""

from __future__ import annotations

import argparse
import random
import sys

from nyx.models import MODELS
from nyx.paths import local_dir
from nyx.wake.calibrate import (
    PERSONAL_MODEL,
    Builder,
    Recordings,
    Score,
    evaluate,
    finetune,
    load_base,
)
from nyx.wake.features import FeatureExtractor
from nyx.wake.net import export_onnx


def line(name: str, s: Score) -> str:
    return (
        f"{name:22} aciertos {s.hits}/{s.total} ({100 * s.recall:.0f} %) · "
        f"saltos en uso normal {s.false_triggers} ({s.false_per_hour:.1f}/h, sin whisper)"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--solo-medir", action="store_true")
    parser.add_argument("--umbral", type=float, default=0.5)
    args = parser.parse_args()

    rec = Recordings.load(local_dir() / "training" / "grabaciones")
    if len(rec.positives) < 20 or not rec.ambient:
        print("Faltan grabaciones: scripts/record_samples.py positivos y continuo")
        return 1
    fx = FeatureExtractor(MODELS["wake-melspec"].path(), MODELS["wake-embedding"].path(), 4)
    print(
        f"Tus grabaciones: {len(rec.positives)} «Nyx», {len(rec.lookalikes)} parecidas, "
        f"{len(rec.ambient)} trozos de uso normal",
        flush=True,
    )

    halves = [
        (rec.positives[0::2], rec.positives[1::2]),
        (rec.positives[1::2], rec.positives[0::2]),
    ]
    amb = [(rec.ambient[0::2], rec.ambient[1::2]), (rec.ambient[1::2], rec.ambient[0::2])]
    base = load_base()
    totals = {"base": [0, 0, 0, 0.0], "calibrado": [0, 0, 0, 0.0]}
    for fold, ((train_pos, test_pos), (train_amb, test_amb)) in enumerate(
        zip(halves, amb, strict=True), 1
    ):
        b = evaluate(base, fx, test_pos, test_amb, args.umbral)
        builder = Builder(fx, train_amb, random.Random(fold))
        pos, neg = builder.dataset(train_pos, rec.lookalikes)
        tuned = finetune(pos, neg)
        c = evaluate(tuned, fx, test_pos, test_amb, args.umbral)
        print(f"Mitad {fold}:")
        print("  " + line("modelo base", b))
        print("  " + line("calibrado", c), flush=True)
        for key, s in (("base", b), ("calibrado", c)):
            t = totals[key]
            t[0] += s.hits
            t[1] += s.total
            t[2] += s.false_triggers
            t[3] += s.hours
    summary = {k: Score(int(v[0]), int(v[1]), int(v[2]), float(v[3])) for k, v in totals.items()}
    print("\nEn conjunto (siempre medido con lo que no se usó para ajustar):")
    for key, s in summary.items():
        print("  " + line(key, s))
    better = summary["calibrado"].recall >= summary["base"].recall and (
        summary["calibrado"].false_per_hour <= summary["base"].false_per_hour * 1.5 + 2
    )
    if args.solo_medir:
        return 0
    if not better:
        print("\nLa calibración no mejora: se queda el modelo base.")
        return 0
    builder = Builder(fx, rec.ambient, random.Random(99))
    pos, neg = builder.dataset(rec.positives, rec.lookalikes)
    export_onnx(finetune(pos, neg), PERSONAL_MODEL)
    print(f"\nGuardado {PERSONAL_MODEL}. Reinicia el núcleo (bandeja) para usarlo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
