"""Servidor de prueba con la API de Ollama (6.27, paso 5): mide el LoRA sin pasar por Ollama.

Ollama 0.40 ya no importa un Qwen2 ajustado (ni `q4_K_M` desde safetensors, ni adaptadores
LoRA, ni Qwen2 en su importador MLX) y convertirlo a GGUF necesita llama.cpp. Para saber
antes si el LoRA merece la pena, este servidor responde a `/api/chat` como Ollama con el
modelo de 4 bits de Unsloth, en dos variantes del mismo modelo cargado una sola vez:

- `base`: Qwen2.5-7B-Instruct sin el LoRA (el adaptador desactivado).
- `lora`: con el LoRA de `output/lora`.

Así la batería (`scripts/battery.py --host http://127.0.0.1:11500 --modelo lora`) compara los
dos en igualdad: mismo motor, mismo prompt (el texto lo arma `render`, el de entrenar, que
copia la plantilla de Ollama) y misma semilla. No sustituye a la medida final con Ollama.

Solo escucha en 127.0.0.1. Uso, con el entorno de entrenamiento y desde core/training/llm:

    .venv/Scripts/python.exe serve.py
"""

from __future__ import annotations

import os

os.environ.setdefault("HIP_VISIBLE_DEVICES", "0")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

# Unsloth antes que transformers (lo pide él).
from unsloth import FastLanguageModel  # noqa: I001

import argparse
import contextlib
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import torch

from train import render

HERE = Path(__file__).resolve().parent
_BLOCK = re.compile(r"<tool_call>(.*?)(?:</tool_call>|$)", re.S)


def parse(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Texto y llamadas, como el analizador de qwen2.5 en Ollama: cada línea JSON dentro de
    `<tool_call>` es una llamada; lo que no se entiende se queda como texto."""
    calls: list[dict[str, Any]] = []
    for block in _BLOCK.findall(text):
        for line in block.strip().splitlines():
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(raw, dict) and "name" in raw:
                calls.append(
                    {"function": {"name": raw["name"], "arguments": raw.get("arguments") or {}}}
                )
    if not calls:
        return text, []
    return text[: text.find("<tool_call>")].strip(), calls


class Model:
    def __init__(self, lora: Path, max_new_tokens: int) -> None:
        self.model, self.tokenizer = FastLanguageModel.from_pretrained(
            model_name=str(lora), max_seq_length=12288, load_in_4bit=True
        )
        FastLanguageModel.for_inference(self.model)
        self.max_new_tokens = max_new_tokens
        self.lock = threading.Lock()  # una petición cada vez, como Ollama con un modelo

    def generate(self, name: str, body: dict[str, Any]) -> tuple[str, list[dict[str, Any]], float]:
        options = body.get("options") or {}
        # Como la plantilla de Ollama: tras el último mensaje del usuario, el turno de Nyx.
        prompt = render(body.get("messages") or [], body.get("tools") or [])
        prompt += "<|im_start|>assistant\n"
        ids = self.tokenizer(prompt, return_tensors="pt", add_special_tokens=False).to("cuda")
        temperature = float(options.get("temperature", 0.3))
        limit = int(options.get("num_predict", self.max_new_tokens))
        if limit < 0:
            limit = self.max_new_tokens
        with self.lock:
            if (seed := options.get("seed")) is not None:
                torch.manual_seed(int(seed))
            adapter = contextlib.nullcontext() if name == "lora" else self.model.disable_adapter()
            t0 = time.perf_counter()
            with adapter, torch.inference_mode():
                out = self.model.generate(
                    **ids,
                    max_new_tokens=limit,
                    do_sample=temperature > 0,
                    temperature=temperature if temperature > 0 else None,
                    top_p=None,
                    top_k=None,
                    eos_token_id=self.tokenizer.convert_tokens_to_ids("<|im_end|>"),
                    pad_token_id=self.tokenizer.eos_token_id,
                )
            took = time.perf_counter() - t0
        new = out[0][ids["input_ids"].shape[1] :]
        text = self.tokenizer.decode(new, skip_special_tokens=True)
        content, calls = parse(text)
        if not calls and "<tool_call>" in text:  # llamada rota: se ve con los tokens especiales
            print("  crudo:", [self.tokenizer.decode([i]) for i in new[:24]], flush=True)
        return content, calls, took


def handler(model: Model) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass  # sin una línea por petición: ya se escribe una por respuesta

        def _send(self, payload: bytes, status: int = 200, kind: str = "application/json") -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:
            if self.path == "/api/version":
                self._send(b'{"version":"nyx-lora-test"}')
            else:
                self._send(b'{"error":"not found"}', 404)

        def do_POST(self) -> None:
            size = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(size) or b"{}")
            if self.path == "/api/generate":  # descargar el modelo: aquí no hace nada
                self._send(b'{"done":true}')
                return
            if self.path != "/api/chat":
                self._send(b'{"error":"not found"}', 404)
                return
            name = str(body.get("model", ""))
            if name not in ("base", "lora"):
                self._send(json.dumps({"error": f"model '{name}' not found"}).encode(), 404)
                return
            content, calls, took = model.generate(name, body)
            message: dict[str, Any] = {"role": "assistant", "content": content}
            if calls:
                message["tool_calls"] = calls
            chunk = {"model": name, "message": message, "done": True, "total_duration": took}
            line = json.dumps(chunk, ensure_ascii=False) + "\n"
            # Con stream o sin él, un solo trozo final: la batería lee igual las dos cosas.
            self._send(line.encode("utf-8"), kind="application/x-ndjson")
            print(f"{name:4} {took:5.1f} s · {len(calls)} llamadas · {content[:60]!r}", flush=True)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--puerto", type=int, default=11500)
    parser.add_argument("--lora", type=Path, default=HERE / "output" / "lora")
    parser.add_argument("--max-tokens", type=int, default=320)
    args = parser.parse_args()
    model = Model(args.lora, args.max_tokens)
    server = ThreadingHTTPServer(("127.0.0.1", args.puerto), handler(model))
    print(f"Listo en http://127.0.0.1:{args.puerto} (modelos: base, lora)", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
