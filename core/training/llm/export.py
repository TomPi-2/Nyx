"""Exporta el LoRA a Ollama (6.27, paso 4): une el LoRA al modelo y crea `nyx-qwen2.5:7b`.

Con el entorno de entrenamiento, desde core/training/llm:

    .venv/Scripts/python.exe export.py

1. Une `output/lora` a Qwen2.5-7B-Instruct en 16 bits (`output/merged`, ~15 GB en disco).
2. Escribe un Modelfile con la misma plantilla, sistema y parámetros que `qwen2.5:7b` de
   Ollama (así Nyx lo usa igual) y crea el modelo cuantizado a q4_K_M (~4,7 GB, como el
   original). Ollama lo ejecuta con Vulkan: nada de ROCm en Nyx.

Nyx no lo usa hasta que se elija en sus ajustes (`llm.model`), tras medirlo (paso 5).
"""

from __future__ import annotations

import os

os.environ.setdefault("HIP_VISIBLE_DEVICES", "0")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

# Unsloth antes que trl y transformers (lo pide él).
from unsloth import FastLanguageModel  # noqa: I001

import argparse
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"


def modelfile(merged: Path, base: str) -> str:
    """El Modelfile de `base` en Ollama, cambiando solo de dónde salen los pesos."""
    original = subprocess.run(
        ["ollama", "show", base, "--modelfile"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    lines = [ln for ln in original.splitlines() if not ln.startswith(("FROM ", "#"))]
    return f"FROM {merged.as_posix()}\n" + "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--nombre", default="nyx-qwen2.5:7b")
    parser.add_argument("--base", default="qwen2.5:7b", help="modelo de Ollama a imitar")
    parser.add_argument("--cuantizar", default="q4_K_M")
    args = parser.parse_args()

    merged = OUT / "merged"
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(OUT / "lora"), max_seq_length=8192, load_in_4bit=True
    )
    model.save_pretrained_merged(str(merged), tokenizer, save_method="merged_16bit")
    path = OUT / "Modelfile"
    path.write_text(modelfile(merged, args.base), encoding="utf-8")
    subprocess.run(
        ["ollama", "create", args.nombre, "-f", str(path), "--quantize", args.cuantizar], check=True
    )
    print(f"Creado {args.nombre}. Probar: uv run python scripts/battery.py --modelo {args.nombre}")


if __name__ == "__main__":
    main()
