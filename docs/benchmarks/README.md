# Pruebas de rendimiento

Informes JSON de las pruebas técnicas, uno por equipo y fecha. Sirven para fijar los requisitos mínimos de Nyx comparando el PC de referencia (RX 7700 XT) con el portátil (RTX 3070 Laptop).

## Ollama (LLM)

1. Instala Ollama desde https://ollama.com.
2. Descarga los modelos candidatos: `ollama pull qwen2.5:7b` y `ollama pull llama3.1:8b`.
3. Desde `core/`: `uv run python scripts/check_ollama.py`

Mide la carga, la VRAM, el % del modelo en GPU, el tiempo hasta el primer token (objetivo < 1,5 s), los tokens/s y el acierto eligiendo herramientas.

## whisper.cpp (voz a texto)

1. Consigue `whisper-server.exe` con Vulkan: mira si la [última release](https://github.com/ggml-org/whisper.cpp/releases) trae binarios de Windows con Vulkan; si no, compílalo con el [Vulkan SDK](https://vulkan.lunarg.com/) y `cmake -B build -DGGML_VULKAN=1 && cmake --build build --config Release`.
2. Descarga `ggml-large-v3-turbo-q5_0.bin` de https://huggingface.co/ggerganov/whisper.cpp.
3. Desde `core/`: `uv run python scripts/check_whisper.py --server <ruta>\whisper-server.exe --model <ruta>\ggml-large-v3-turbo-q5_0.bin`

Sin `--audio`, genera tres frases con la voz española de Windows. Revisa en el informe (`backend`) que use Vulkan y no la CPU.
