# Ajuste fino (LoRA) del cerebro de Nyx · tarea 6.27

Herramienta de desarrollo: **no se distribuye con Nyx**. Entrena un LoRA sobre `qwen2.5:7b`
para que actúe en vez de contestar en texto y escriba bien la cabecera de los paneles. El
resultado se exporta a GGUF y se carga en Ollama, que lo ejecuta con Vulkan como siempre: Nyx
no usa ROCm ni CUDA.

## Entorno (PC con RX 7700 XT, Windows, ROCm)

Entorno propio, separado del de Nyx (`core/.venv`), para que PyTorch y Unsloth no se mezclen:

```powershell
cd core/training/llm
$env:UV_LINK_MODE = "copy"   # la caché de uv está en una carpeta sincronizada (ver CLAUDE.md)
uv venv --python 3.12 .venv
# PyTorch de AMD para Windows (lleva su propio runtime de ROCm: no hace falta el HIP SDK).
# El índice de AMD va primero; uv solo mira el primer índice que tiene un paquete.
uv pip install --python .venv/Scripts/python.exe `
  --index https://repo.amd.com/rocm/whl-multi-arch/ --default-index https://pypi.org/simple `
  "torch[device-gfx1101]==2.11.0+rocm7.14.0" "torchvision[device-gfx1101]==0.26.0+rocm7.14.0"
# Unsloth solo de PyPI (el índice de AMD contesta 403 a lo que no tiene), sin dejar que cambie
# el torch de AMD por el de CUDA:
uv pip install --python .venv/Scripts/python.exe --overrides torch-pins.txt "unsloth[amd]"
```

Versiones probadas el 2026-11-13: torch 2.11.0+rocm7.14.0, Unsloth 2026.11.4, TRL 1.15.0,
transformers 5.17.0, bitsandbytes 0.50.2.

**Nunca** `uv pip install -U unsloth` ni `--force-reinstall` sin `--overrides torch-pins.txt`:
cambiaría el torch de AMD por el de CUDA (aviso de Unsloth).

## Prueba corta

```powershell
.venv/Scripts/python.exe probe.py            # ¿ve PyTorch la gráfica?
.venv/Scripts/python.exe probe.py --entrenar # 20 pasos de QLoRA con Qwen2.5 0,5B
```

Resultado en el PC de referencia (2026-11-13): RX 7700 XT, 12 GB; 20 pasos en 10 s; la pérdida
baja de 4,2 a 0,42; pico de 0,7 GB.

Notas:

- `HIP_VISIBLE_DEVICES=0`: la gráfica integrada del Ryzen también aparece como dispositivo
  ROCm y, con ella, Unsloth da el bf16 por no soportado. Con solo la dedicada, bf16 sí.
- TRL 1.x: `SFTTrainer(processing_class=…)`, ya no `tokenizer=…`; e `import unsloth` antes que
  `trl` y `transformers`.
- Antes de entrenar el 7B: cerrar Nyx y sacar el modelo de Ollama de la gráfica (no caben los
  dos en 12 GB).

## Entrenar, medir y exportar

```powershell
.venv/Scripts/python.exe make_dataset.py juntar --maximo 1000   # data/train.jsonl y valid.jsonl
./entrenar.ps1                       # en segundo plano; output/train.log, reanuda si se corta
.venv/Scripts/python.exe serve.py    # API de Ollama en 127.0.0.1:11500: modelos «base» y «lora»
# desde core/, con el entorno de Nyx:
uv run python scripts/battery.py --frases tests/battery/reserva.jsonl --host http://127.0.0.1:11500 --modelo lora
```

`serve.py` compara el modelo con y sin el LoRA en el mismo motor (transformers en 4 bits), con
el mismo prompt que Ollama (`render`) y la misma semilla. Sirve para decidir si el LoRA merece
la pena; las latencias no cuentan (sin caché de prefijo ni streaming).

**Exportar a Ollama.** Ollama 0.40 ya no importa este modelo por sí solo: desde safetensors
solo cuantiza a int4/int8/nvfp4, su importador nuevo (MLX) no admite Qwen2, ya no acepta
adaptadores LoRA y no cuantiza un GGUF. El camino es GGUF con llama.cpp (MIT, solo para
desarrollo; nada de esto va en Nyx). Probado el 2026-11-13 con la ronda 1:

```powershell
.venv/Scripts/python.exe export.py   # une en output/merged (16 bits, ~15 GB) y escribe el Modelfile
# Una vez: el conversor (en Python) y llama-quantize (release oficial para Windows, CPU).
git clone --depth 1 https://github.com/ggml-org/llama.cpp output/llama.cpp
uv pip install --python .venv/Scripts/python.exe gguf   # misma versión que output/llama.cpp/gguf-py
# output/llama-bin: llama-b12360-bin-win-cpu-x64.zip de github.com/ggml-org/llama.cpp/releases,
# comprobando su SHA-256 con el «digest» que publica la release.
.venv/Scripts/python.exe output/llama.cpp/convert_hf_to_gguf.py output/merged --outtype f16 --outfile output/nyx-f16.gguf
output/llama-bin/llama-quantize.exe output/nyx-f16.gguf output/nyx-q4_k_m.gguf Q4_K_M   # ~1 min, 4,7 GB
.venv/Scripts/python.exe export.py --sin-unir   # crea nyx-qwen2.5:7b y comprueba que es igual que qwen2.5:7b
```

`export.py` copia la plantilla, el sistema y los parámetros de `qwen2.5:7b` y comprueba que
quedan iguales byte a byte. Dos trampas encontradas: la plantilla tiene una línea `# Tools` que
no es un comentario, y un Modelfile con saltos de línea de Windows mete retornos de carro en la
plantilla (y en el prompt).

## Licencias (comprobadas antes de usarlas)

Unsloth, transformers, TRL: Apache-2.0 · PyTorch: BSD-3 · bitsandbytes: MIT · llama.cpp
(conversión a GGUF): MIT · Qwen2.5-7B-Instruct: Apache-2.0 (permite distribuir el ajustado).
