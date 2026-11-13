"""Exporta el LoRA a Ollama (6.27, paso 4): une el LoRA al modelo y crea `nyx-qwen2.5:7b`.

Con el entorno de entrenamiento, desde core/training/llm:

    .venv/Scripts/python.exe export.py                  # unir y crear el modelo
    .venv/Scripts/python.exe export.py --sin-unir       # solo el Modelfile y `ollama create`
    .venv/Scripts/python.exe export.py --carpeta output/r1 --nombre nyx-r1:7b --sin-unir

1. Une `<carpeta>/lora` a Qwen2.5-7B-Instruct en 16 bits (`<carpeta>/merged`, ~15 GB).
2. Ollama 0.40 ya no lo importa por sí solo (ni `q4_K_M` desde safetensors, ni adaptadores,
   ni Qwen2 en su importador MLX, ni cuantizar un GGUF): se pasa a GGUF y se cuantiza a
   Q4_K_M con llama.cpp (pasos en el README) en `<carpeta>/nyx-q4_k_m.gguf`.
3. Escribe un Modelfile con la misma plantilla, sistema y parámetros que `qwen2.5:7b` de
   Ollama (así Nyx lo usa igual) y, si el GGUF ya está, crea el modelo y comprueba que la
   plantilla, el sistema y los parámetros quedan idénticos byte a byte. Ollama lo ejecuta con
   Vulkan: nada de ROCm en Nyx.

Nyx no lo usa hasta que se elija en sus ajustes (`llm.model`), tras medirlo (paso 5).
"""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _ollama(*args: str) -> str:
    return subprocess.run(
        ["ollama", *args], capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout


def modelfile(weights: Path, base: str) -> str:
    """El Modelfile de `base` en Ollama, cambiando solo de dónde salen los pesos."""
    # Lo que va tras el FROM, tal cual: la plantilla lleva una línea «# Tools» que no es un
    # comentario (quitarla cambiaba el prompt respecto al del entrenamiento).
    lines = _ollama("show", base, "--modelfile").splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("FROM "))
    return f"FROM {weights.as_posix()}\n" + "\n".join(lines[start + 1 :]) + "\n"


def merge(folder: Path) -> None:
    os.environ.setdefault("HIP_VISIBLE_DEVICES", "0")
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    from unsloth import FastLanguageModel

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(folder / "lora"), max_seq_length=8192, load_in_4bit=True
    )
    model.save_pretrained_merged(str(folder / "merged"), tokenizer, save_method="merged_16bit")


def same_as_base(name: str, base: str) -> list[str]:
    """Lo que difiere entre `name` y `base` (plantilla, sistema, parámetros); [] si nada."""
    keys = ("template", "system", "parameters")
    return [k for k in keys if _ollama("show", name, f"--{k}") != _ollama("show", base, f"--{k}")]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--nombre", default="nyx-qwen2.5:7b")
    parser.add_argument("--base", default="qwen2.5:7b", help="modelo de Ollama a imitar")
    parser.add_argument("--carpeta", type=Path, default=HERE / "output")
    parser.add_argument("--sin-unir", action="store_true", help="<carpeta>/merged ya está hecho")
    args = parser.parse_args()

    folder: Path = args.carpeta.resolve()
    if not args.sin_unir:
        merge(folder)
    gguf = folder / "nyx-q4_k_m.gguf"
    path = folder / "Modelfile"
    # Saltos de línea de Unix: con los de Windows, los retornos de carro acababan en la
    # plantilla y, con ella, en el prompt.
    path.write_text(modelfile(gguf, args.base), encoding="utf-8", newline="\n")
    if not gguf.exists():
        print(f"Unido en {folder / 'merged'}. Falta {gguf.name}: conviértelo con llama.cpp.")
        return
    subprocess.run(["ollama", "create", args.nombre, "-f", str(path)], check=True)
    if differs := same_as_base(args.nombre, args.base):
        raise SystemExit(f"{args.nombre} no es igual que {args.base} en: {', '.join(differs)}")
    print(f"Creado {args.nombre}. Probar: uv run python scripts/battery.py --modelo {args.nombre}")


if __name__ == "__main__":
    main()
