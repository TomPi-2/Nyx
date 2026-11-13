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

## Licencias (comprobadas antes de usarlas)

Unsloth, transformers, TRL: Apache-2.0 · PyTorch: BSD-3 · bitsandbytes: MIT · llama.cpp
(conversión a GGUF): MIT · Qwen2.5-7B-Instruct: Apache-2.0 (permite distribuir el ajustado).
