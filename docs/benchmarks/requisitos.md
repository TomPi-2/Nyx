# Requisitos del sistema

Comparación de los dos equipos de prueba y requisitos que salen de ella. Informes en esta carpeta: `ollama-TomPi-20261109-1754.json` y `whisper-TomPi-20261109-1758.json` (sobremesa); `ollama-DESKTOP-FVKMTP2-20261111-1337.json` y `whisper-DESKTOP-FVKMTP2-20261111-1411.json` (portátil; el de Whisper es de la Radeon integrada, ver abajo). Pruebas del portátil del 2026-11-11, enchufado y en «Máximo rendimiento».

## Equipos

| | Sobremesa (referencia) | Portátil |
| --- | --- | --- |
| Procesador | AMD Ryzen 7 7700X (8 núcleos) | AMD Ryzen 7 6800H (8 núcleos) |
| RAM | 32 GB | 16 GB |
| Tarjeta gráfica | AMD Radeon RX 7700 XT, 12 GB | NVIDIA RTX 3070 Laptop, 8 GB (+ Radeon 680M integrada) |
| Sistema | Windows 11 Pro | Windows 11 Pro |

## Resultados

| Prueba | Sobremesa | Portátil (RTX) | Objetivo (SPEC 14) |
| --- | --- | --- | --- |
| LLM `qwen2.5:7b`: en la GPU | 100 % | 100 % | 100 % |
| LLM: VRAM | 4,43 GB | 4,43 GB | — |
| LLM: carga | 4,7 s | 7,6 s | solo al arrancar |
| LLM: primer token (script) | 0,021 s | 0,021 s | < 1,5 s |
| LLM: velocidad | 77 tokens/s | 83 tokens/s | > 30 |
| LLM: herramienta correcta | 3/3 | 3/3 | 3/3 |
| Whisper large-v3-turbo q5 (Vulkan), script | 0,17 s por frase | no medido en la RTX (el script usó la integrada) | ≤ 0,3 s |
| App: transcripción tras el fin de la frase | — | 0–38 ms (se transcribe mientras hablas) | — |
| App: verificación de «Nyx» con Whisper | — | 427 ms (la primera, 1.207 ms) | — |
| App: fin de la frase → voz, pregunta sencilla | — | 387 ms | < 1,5 s |
| App: fin de la frase → voz, con herramienta del LLM | — | 1.284 ms | < 1,5 s |
| App: primer token, petición escrita | — | 0,31–0,66 s (8 peticiones) | < 1,5 s |
| App: acción por regla (escrita) | — | 3 ms (ajustes), 546 ms (volumen) | < 500 ms |
| App: arranque hasta «servicios listos» | — | 6,5–7,9 s sin Whisper; **23,3 s** con Whisper (primera vez) | < 10 s |
| App en reposo: CPU | — | 0,1–1,1 % | < 2 % |
| App en reposo: RAM del núcleo | — | ~800 MB | < 600 MB |
| App en reposo: VRAM dedicada (todo el equipo) | — | 5,0 de 8 GB sin Whisper (≈ 5,6 con él) | ≈ 7–8 GB |

Notas:

- En el portátil Ollama usa CUDA (lo normal con NVIDIA); el código de Nyx sigue sin depender de CUDA.
- La RTX 3070 Laptop rinde igual o algo mejor que la RX 7700 XT con el modelo de 7B, porque cabe entero en la GPU. El cuello de botella es la VRAM, no la potencia.
- La voz cumple los objetivos en el portátil: 0,4 s en una pregunta sencilla y 1,3 s cuando el LLM usa una herramienta (dos llamadas).
- Con Whisper, unos 5,6 GB de VRAM (sumando sus 0,57 GB). En una tarjeta de 8 GB quedan unos 2,4 GB para un juego; en partida el LLM puede descargarse (`game.unload_llm_after_min`).
- **Arranque de 23,3 s con Whisper**, por encima del objetivo de 10 s. Según el registro: whisper-server arranca primero en la integrada (4,2 s), se relanza en la RTX (1,6 s) y la transcripción de calentamiento tarda ~17 s, probablemente porque el controlador compila los shaders de Vulkan la primera vez. Hay que volver a medirlo en un segundo arranque (apuntado en `docs/ERRORES.md`).
- La RAM del núcleo (~800 MB) supera el objetivo de 600 MB. En el sobremesa no se ha medido; hay que comparar antes de decidir si es un problema.
- El volumen tardó 546 ms en una petición escrita, así que es el tiempo de la propia acción, no del reconocimiento de voz. Hay que ver si se repite.

### Whisper en el portátil

- **Compilación:** el `whisper-server.exe` copiado del sobremesa (compilado con `GGML_NATIVE=ON`, con AVX-512 del Zen 4) se caía en el Ryzen 7 6800H con 0xC000001D en `ggml-cpu.dll`. Recompilado en el portátil con las opciones portables de `README.md` (sección 3), funciona y elige solo la variante `ggml-cpu-haswell.dll`. El whisper-server que se distribuya con Nyx tiene que compilarse así.
- **Gráfica integrada (Radeon 680M):** `check_whisper.py` no elige tarjeta y usó la integrada (dispositivo Vulkan 0). Devolvió «!!!!…» en las tres frases y tardó ~10 s por frase. Nyx sí elige bien: arranca, ve las dos tarjetas y se relanza en la RTX.

## Requisitos

| | Mínimos (probado: portátil) | Recomendados (probado: sobremesa) |
| --- | --- | --- |
| Sistema | Windows 11 de 64 bits | Windows 11 de 64 bits |
| Tarjeta gráfica | **Dedicada**, compatible con Vulkan y con **8 GB de VRAM** (por ejemplo RTX 3070 Laptop) | 12 GB de VRAM (por ejemplo RX 7700 XT); necesarios para el modelo de 14B |
| Procesador | 8 núcleos de la generación del Ryzen 7 6800H (AVX2) | Ryzen 7 7700X o similar |
| RAM | 16 GB | 32 GB |
| Disco | ~8 GB libres (LLM 4,7 GB y modelos de voz ~1 GB) | ~9 GB más para el modelo de 14B |
| Otros | Micrófono; portátil enchufado para el rendimiento completo | — |

- **¿Por qué 8 GB y no 6?** Con 6 GB, el LLM y Whisper (~5 GB) caben en teoría, pero no quedaría sitio para Windows ni para un juego, y no se ha probado. No se promete lo que no se ha probado. El asistente recomienda hoy el 7B a partir de 6 GB (`core/nyx/setup/hardware.py`). Se puede dejar así (cabe) o subirlo a 8 si se quieren alinear.
- Con menos VRAM, Ollama reparte el modelo entre la GPU y la CPU. Funciona, pero lento: deja de cumplir el objetivo de 1,5 s.
- **Solo con gráfica integrada no sirve:** en la Radeon 680M, Whisper transcribe basura y tarda ~10 s por frase.
- Pendiente: el arranque con Whisper (23 s la primera vez) y la RAM del núcleo, que superan sus objetivos.
