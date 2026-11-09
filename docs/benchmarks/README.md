# Pruebas de rendimiento

Informes JSON de las pruebas técnicas, uno por equipo y fecha (`<prueba>-<equipo>-<fecha>.json`). Sirven para fijar los requisitos mínimos de Nyx comparando el PC de referencia (RX 7700 XT) con el portátil (RTX 3070 Laptop). Haz las dos pruebas en cada equipo y sube los informes al repositorio.

Herramientas externas en `C:\dev\tools` (fuera del repositorio).

## 1. Preparar el equipo (una vez)

En PowerShell:

```powershell
winget install Ollama.Ollama
winget install Kitware.CMake
winget install KhronosGroup.VulkanSDK
```

- Si winget no encuentra el Vulkan SDK, descárgalo de https://vulkan.lunarg.com/sdk/home (Windows, instalación por defecto).
- Hace falta Visual Studio 2022 (o Build Tools) con "Desarrollo para el escritorio con C++".
- Cierra y vuelve a abrir la terminal para que se apliquen las variables `PATH` y `VULKAN_SDK`.

Comprueba: `ollama --version`, `cmake --version` y `echo $env:VULKAN_SDK`.

## 2. Prueba del LLM (Ollama)

1. Abre Ollama (se queda en la bandeja) y descarga los dos modelos candidatos, unos 5 GB cada uno:

   ```powershell
   ollama pull qwen2.5:7b
   ollama pull llama3.1:8b
   ```

2. Cierra juegos y apps que usen mucha GPU, y ejecuta desde `core/`:

   ```powershell
   uv run python scripts/check_ollama.py
   ```

Tarda 2–4 minutos. Por cada modelo mide:

| Dato | Qué significa | Objetivo |
| --- | --- | --- |
| `load_s` | Tiempo en cargar el modelo | Solo al arrancar Nyx |
| `vram_gb` | VRAM que ocupa | Que quepa con Whisper: unos 7–8 GB en total |
| `gpu_percent` | Parte del modelo en la GPU | 100 %; si es menor, va en parte por CPU y será lento |
| `ttft_s` | Tiempo hasta la primera palabra | < 1,5 s |
| `tokens_per_s` | Velocidad al generar | Cuanto más, mejor (> 30 es cómodo) |
| `tool_hits` | Herramienta correcta en 3 peticiones | 3/3 |

En el PC con la RX 7700 XT, Ollama usa la GPU AMD (ROCm). En el portátil usa la RTX con CUDA, que es lo que tendría un usuario con NVIDIA.

## 3. Prueba de voz a texto (whisper.cpp con Vulkan)

Las releases de whisper.cpp para Windows no traen versión Vulkan, así que se compila una vez (unos 5–10 minutos):

```powershell
git clone https://github.com/ggml-org/whisper.cpp C:\dev\tools\whisper.cpp
cd C:\dev\tools\whisper.cpp
cmake -B build -DGGML_VULKAN=1
cmake --build build --config Release -j
```

El servidor queda en `C:\dev\tools\whisper.cpp\build\bin\Release\whisper-server.exe`.

Descarga el modelo (unos 550 MB):

```powershell
New-Item -ItemType Directory -Force C:\dev\tools\models
curl.exe -L -o C:\dev\tools\models\ggml-large-v3-turbo-q5_0.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo-q5_0.bin
```

Ejecuta desde `core/`:

```powershell
uv run python scripts/check_whisper.py --server C:\dev\tools\whisper.cpp\build\bin\Release\whisper-server.exe --model C:\dev\tools\models\ggml-large-v3-turbo-q5_0.bin
```

Genera tres frases en español con la voz de Windows y mide cuánto tarda en transcribir cada una con el modelo ya cargado (como hará Nyx). Revisa en el informe:

- `backend`: debe nombrar Vulkan y tu GPU. Si no aparece, está usando la CPU.
- `text`: la transcripción tiene que coincidir con la frase.
- `median_latency_s`: objetivo de unos 0,3 s o menos por frase corta, para que el total "fin de la frase → acción" quede por debajo de 0,5 s.

**Portátil con dos GPU:** Vulkan puede elegir la Radeon integrada en vez de la RTX. Si `backend` nombra "AMD Radeon(TM) Graphics", repite la prueba con `$env:GGML_VK_VISIBLE_DEVICES = "1"` antes del comando, o `"0"` si esa es la RTX.

## 4. Subir los resultados

Los informes se guardan en esta carpeta. Súbelos con `git add docs/benchmarks` + commit, o pásale a Claude la salida de la consola.
