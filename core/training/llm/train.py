"""Entrena el LoRA del cerebro (6.27, paso 3): QLoRA de 4 bits sobre Qwen2.5-7B-Instruct.

Con el entorno de entrenamiento (no el de Nyx), desde core/training/llm:

    .venv/Scripts/python.exe train.py                 # data/train.jsonl → output/lora
    .venv/Scripts/python.exe train.py --pasos 30      # prueba corta

Antes: cerrar Nyx y sacar el modelo de Ollama de la gráfica (no caben los dos en 12 GB).

El texto de cada ejemplo se arma copiando la plantilla de Ollama para qwen2.5 (`ollama show
qwen2.5:7b --template`), no la de Hugging Face: Ollama pone varias llamadas en un solo bloque
<tool_call> y es él quien lee la salida del modelo. Solo se aprende la respuesta del asistente.
"""

from __future__ import annotations

import os

# Solo la gráfica dedicada (la integrada del Ryzen también aparece en ROCm).
os.environ.setdefault("HIP_VISIBLE_DEVICES", "0")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

# Unsloth antes que trl y transformers (lo pide él).
from unsloth import FastLanguageModel  # noqa: I001
from unsloth.chat_templates import train_on_responses_only

import argparse
import json
import time
from pathlib import Path
from typing import Any

import torch
from datasets import Dataset
from trl import SFTConfig, SFTTrainer

HERE = Path(__file__).resolve().parent
BASE = "unsloth/Qwen2.5-7B-Instruct-bnb-4bit"  # Apache-2.0, ya en 4 bits (~5,5 GB)

TOOLS_HEAD = (
    "\n\n# Tools\n\nYou may call one or more functions to assist with the user query.\n\n"
    "You are provided with function signatures within <tools></tools> XML tags:\n<tools>"
)
TOOLS_TAIL = (
    "\n</tools>\n\nFor each function call, return a json object with function name and "
    "arguments within <tool_call></tool_call> XML tags:\n<tool_call>\n"
    '{"name": <function-name>, "arguments": <args-json-object>}\n</tool_call>'
)


def _compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def render(messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> str:
    """El mismo texto que arma Ollama con su plantilla de qwen2.5 (ver docstring)."""
    out = []
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    head = "<|im_start|>system"
    if system:
        head += "\n" + system
    if tools:
        head += TOOLS_HEAD
        for tool in tools:
            head += '\n{"type": "function", "function": ' + _compact(tool["function"]) + "}"
        head += TOOLS_TAIL
    out.append(head + "<|im_end|>\n")
    rest = [m for m in messages if m["role"] != "system"]
    for i, m in enumerate(rest):
        last = i == len(rest) - 1
        if m["role"] == "user":
            out.append(f"<|im_start|>user\n{m['content']}<|im_end|>\n")
        elif m["role"] == "assistant":
            body = m.get("content") or ""
            if not body and m.get("tool_calls"):
                lines = "".join(
                    f'{{"name": "{c["function"]["name"]}", "arguments": '
                    f"{_compact(c['function']['arguments'])}}}\n"
                    for c in m["tool_calls"]
                )
                body = f"<tool_call>\n{lines}</tool_call>"
            out.append(f"<|im_start|>assistant\n{body}<|im_end|>" + ("" if last else "\n"))
    return "".join(out)


def load(path: Path) -> Dataset:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return Dataset.from_dict({"text": [render(r["messages"], r["tools"]) for r in rows]})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pasos", type=int, default=-1, help="-1 = las épocas enteras")
    parser.add_argument("--epocas", type=float, default=1.0)
    parser.add_argument("--rango", type=int, default=16, help="rango del LoRA")
    parser.add_argument("--contexto", type=int, default=8192)
    args = parser.parse_args()

    train = load(HERE / "data" / "train.jsonl")
    # Validación pequeña y solo al final: en esta gráfica medirla cuesta casi como entrenar.
    valid_all = load(HERE / "data" / "valid.jsonl")
    valid = valid_all.select(range(min(24, len(valid_all))))
    print(f"{len(train)} ejemplos para entrenar, {len(valid)} para validar")

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE, max_seq_length=args.contexto, load_in_4bit=True
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=args.rango,
        lora_alpha=args.rango,
        lora_dropout=0,
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        use_gradient_checkpointing="unsloth",  # contextos largos (el prompt y las herramientas)
        random_state=627,
    )
    bf16 = torch.cuda.is_bf16_supported()
    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=train,
        eval_dataset=valid,
        args=SFTConfig(
            dataset_text_field="text",
            max_length=args.contexto,
            per_device_train_batch_size=1,
            gradient_accumulation_steps=8,
            num_train_epochs=args.epocas,
            max_steps=args.pasos,
            learning_rate=2e-4,
            lr_scheduler_type="cosine",
            warmup_steps=10,
            logging_steps=10,
            eval_strategy="no",
            save_steps=20,  # si se corta (sesión, apagón), se retoma desde aquí
            save_total_limit=2,
            bf16=bf16,
            fp16=not bf16,
            optim="adamw_8bit",
            seed=627,
            output_dir=str(HERE / "output" / "checkpoints"),
            report_to="none",
        ),
    )
    # Solo cuenta lo que dice el asistente (no el prompt ni las herramientas).
    trainer = train_on_responses_only(
        trainer,
        instruction_part="<|im_start|>user\n",
        response_part="<|im_start|>assistant\n",
    )
    t0 = time.perf_counter()
    checkpoints = HERE / "output" / "checkpoints"
    resume = any(checkpoints.glob("checkpoint-*")) if checkpoints.exists() else False
    if resume:
        print("Retomando desde el último guardado")
    stats = trainer.train(resume_from_checkpoint=resume or None)
    minutes = (time.perf_counter() - t0) / 60
    peak = torch.cuda.max_memory_allocated() / 2**30
    print(f"Hecho en {minutes:.0f} min · pérdida {stats.training_loss:.3f} · pico {peak:.1f} GB")
    model.save_pretrained(str(HERE / "output" / "lora"))
    tokenizer.save_pretrained(str(HERE / "output" / "lora"))
    metrics = trainer.evaluate()
    print(
        f"Validación ({len(valid)} ejemplos): pérdida {metrics.get('eval_loss', float('nan')):.3f}"
    )


if __name__ == "__main__":
    main()
