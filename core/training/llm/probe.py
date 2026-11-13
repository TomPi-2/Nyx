"""Prueba corta (6.27, paso 1): ¿entrena la gráfica AMD en Windows?

1. PyTorch ve la gráfica por ROCm (en PyTorch, ROCm se presenta como «cuda»).
2. Una multiplicación de matrices en la gráfica.
3. Si se pide (--entrenar), 20 pasos de QLoRA de 4 bits con Unsloth sobre un modelo pequeño
   (Qwen2.5 0,5B) y unas frases de juguete: que la pérdida baje y no reviente la memoria.

Uso (desde core/training/llm, con su propio entorno, no el de Nyx):
    .venv/Scripts/python.exe probe.py
    .venv/Scripts/python.exe probe.py --entrenar
"""

from __future__ import annotations

import argparse
import os
import time

# Solo la gráfica dedicada: la integrada del Ryzen también aparece como dispositivo ROCm.
os.environ.setdefault("HIP_VISIBLE_DEVICES", "0")


def check_gpu() -> None:
    import torch

    print(f"PyTorch {torch.__version__} · HIP {getattr(torch.version, 'hip', None)}")
    if not torch.cuda.is_available():
        raise SystemExit("PyTorch no ve la gráfica (ROCm no disponible)")
    name = torch.cuda.get_device_name(0)
    total = torch.cuda.get_device_properties(0).total_memory / 2**30
    print(f"Gráfica: {name} · {total:.1f} GB")
    a = torch.randn(4096, 4096, device="cuda", dtype=torch.float16)
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    for _ in range(20):
        a = a @ a
        a = a / a.norm()
    torch.cuda.synchronize()
    tflops = 20 * 2 * 4096**3 / (time.perf_counter() - t0) / 1e12
    print(f"Multiplicación de matrices en fp16: {tflops:.1f} TFLOPS")


def train_tiny() -> None:
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")  # Unsloth: descargas en AMD
    from unsloth import FastLanguageModel  # antes que trl y transformers (lo pide Unsloth)

    import torch
    from datasets import Dataset
    from trl import SFTConfig, SFTTrainer

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name="unsloth/Qwen2.5-0.5B-Instruct",
        max_seq_length=512,
        load_in_4bit=True,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        lora_alpha=16,
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
    )
    pairs = [
        ("abre Spotify", "Abriendo Spotify."),
        ("pon el volumen al 20", "Volumen al 20."),
        ("¿qué hora es?", "Son las cinco."),
        ("cierra el Discord", "Cerrando Discord."),
    ] * 20
    texts = [
        tokenizer.apply_chat_template(
            [{"role": "user", "content": q}, {"role": "assistant", "content": a}], tokenize=False
        )
        for q, a in pairs
    ]
    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=Dataset.from_dict({"text": texts}),
        args=SFTConfig(
            dataset_text_field="text",
            per_device_train_batch_size=4,
            gradient_accumulation_steps=1,
            max_steps=20,
            learning_rate=2e-4,
            logging_steps=5,
            # Con solo la dedicada, RDNA 3 admite bf16 (más estable para entrenar).
            bf16=torch.cuda.is_bf16_supported(),
            fp16=not torch.cuda.is_bf16_supported(),
            output_dir="output/probe",
            report_to="none",
        ),
    )
    t0 = time.perf_counter()
    stats = trainer.train()

    peak = torch.cuda.max_memory_allocated() / 2**30
    print(
        f"20 pasos en {time.perf_counter() - t0:.0f} s · pérdida final {stats.training_loss:.3f} "
        f"· pico de memoria {peak:.1f} GB"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--entrenar", action="store_true", help="también 20 pasos de QLoRA")
    args = parser.parse_args()
    check_gpu()
    if args.entrenar:
        train_tiny()
