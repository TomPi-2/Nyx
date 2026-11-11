# Requisitos del sistema

Comparación de los dos equipos de prueba y requisitos que salen de ella. Informes en esta carpeta: `ollama-TomPi-20261109-1754.json` y `whisper-TomPi-20261109-1758.json` (sobremesa) y `ollama-DESKTOP-FVKMTP2-20261111-1337.json` (portátil). Pruebas del portátil del 2026-11-11, enchufado y en «Máximo rendimiento».

## Equipos

| | Sobremesa (referencia) | Portátil |
| --- | --- | --- |
| Procesador | AMD Ryzen 7 7700X (8 núcleos) | AMD Ryzen 7 6800H (8 núcleos) |
| RAM | 32 GB | 16 GB |
| Tarjeta gráfica | AMD Radeon RX 7700 XT, 12 GB | NVIDIA RTX 3070 Laptop, 8 GB (+ Radeon integrada) |
| Sistema | Windows 11 Pro | Windows 11 Pro |

## Resultados

| Prueba | Sobremesa | Portátil | Objetivo (SPEC 14) |
| --- | --- | --- | --- |
| LLM `qwen2.5:7b`: en la GPU | 100 % | 100 % | 100 % |
| LLM: VRAM | 4,43 GB | 4,43 GB | — |
| LLM: carga | 4,7 s | 7,6 s | solo al arrancar |
| LLM: primer token (script) | 0,021 s | 0,021 s | < 1,5 s |
| LLM: velocidad | 77 tokens/s | 83 tokens/s | > 30 |
| LLM: herramienta correcta | 3/3 | 3/3 | 3/3 |
| Whisper large-v3-turbo q5 (Vulkan) | 0,17 s por frase | **pendiente** (se cae en la Radeon integrada, ver abajo) | ≤ 0,3 s |
| App: primer token, petición escrita | — | 0,31–0,66 s (8 peticiones) | < 1,5 s |
| App: acción por regla (escrita) | — | 3 ms (ajustes), 546 ms (volumen) | < 500 ms |
| App: arranque hasta «servicios listos» | — | 6,5–7,9 s (una vez 15,2 s) | < 10 s |
| App en reposo: CPU | — | 0,1–1,1 % | < 2 % |
| App en reposo: RAM del núcleo | — | ~800 MB | < 600 MB |
| App en reposo: VRAM dedicada (todo el equipo) | — | 5,0 de 8 GB, sin Whisper | ≈ 7–8 GB |

Notas:

- En el portátil Ollama usa CUDA (lo normal con NVIDIA); el código de Nyx sigue sin depender de CUDA.
- La RTX 3070 Laptop rinde igual o algo mejor que la RX 7700 XT con el modelo de 7B, porque cabe entero en la GPU. El cuello de botella es la VRAM, no la potencia.
- Con Whisper serán unos 5,6 GB (sumando sus 0,57 GB). En una tarjeta de 8 GB quedan unos 2,4 GB para un juego; en partida el LLM puede descargarse (`game.unload_llm_after_min`).
- La RAM del núcleo (~800 MB) supera el objetivo de 600 MB. En el sobremesa no se ha medido; hay que comparar antes de decidir si es un problema.
- El volumen tardó 546 ms en una petición escrita, así que es el tiempo de la propia acción, no del reconocimiento de voz. Hay que ver si se repite.
- Falta la latencia de voz de extremo a extremo (fin de la frase → acción y → primera palabra hablada) en el portátil, porque Whisper no arrancó.

### Whisper en un portátil con dos tarjetas

whisper.cpp numera las tarjetas Vulkan con la Radeon integrada en el 0 y la RTX en el 1. Sin `--device` usa la 0 y el servidor se cae al arrancar, tanto en `check_whisper.py` como en la app (apuntado en `docs/ERRORES.md`). Para medirlo mientras tanto:

```powershell
$env:GGML_VK_VISIBLE_DEVICES = "1"
uv run python scripts/check_whisper.py --server $env:LOCALAPPDATA\Nyx\whisper\whisper-server.exe --model $env:LOCALAPPDATA\Nyx\models\ggml-large-v3-turbo-q5_0.bin
Remove-Item Env:GGML_VK_VISIBLE_DEVICES
```

## Requisitos (provisionales)

Provisionales hasta medir Whisper y la latencia de voz en el portátil.

| | Mínimos (probado: portátil) | Recomendados (probado: sobremesa) |
| --- | --- | --- |
| Sistema | Windows 11 de 64 bits | Windows 11 de 64 bits |
| Tarjeta gráfica | Compatible con Vulkan y **8 GB de VRAM dedicada** (por ejemplo RTX 3070 Laptop) | 12 GB de VRAM (por ejemplo RX 7700 XT); necesarios para el modelo de 14B |
| Procesador | 8 núcleos de la generación del Ryzen 7 6800H | Ryzen 7 7700X o similar |
| RAM | 16 GB | 32 GB |
| Disco | ~8 GB libres (LLM 4,7 GB y modelos de voz ~1 GB) | ~9 GB más para el modelo de 14B |
| Otros | Micrófono; portátil enchufado para el rendimiento completo | — |

- **¿Por qué 8 GB y no 6?** Con 6 GB, el LLM y Whisper (~5 GB) caben en teoría, pero no quedaría sitio para Windows ni para un juego, y no se ha probado. No se promete lo que no se ha probado. El asistente recomienda hoy el 7B a partir de 6 GB (`core/nyx/setup/hardware.py`). Se puede dejar así (cabe) o subirlo a 8 si se quieren alinear.
- Con menos VRAM, Ollama reparte el modelo entre la GPU y la CPU. Funciona, pero lento: deja de cumplir el objetivo de 1,5 s.
- Sin tarjeta dedicada (solo la integrada) no está probado.
