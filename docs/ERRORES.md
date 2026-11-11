# Errores conocidos

Fallos vistos al usar Nyx que quedan pendientes de corregir. Se apuntan aquí para no perderlos y se corrigen por tandas sin parar el plan de fases. Al corregir uno, se mueve a «Corregidos» con la fecha y el commit, y se añade su frase a la batería de pruebas (`core/tests`).

## Pendientes

| Fecha | Frase o situación | Qué pasa | Qué debería pasar | Pista |
| --- | --- | --- | --- | --- |
| 2026-11-10 | «Explícame qué es un agujero negro» (escrito, portátil) | Responde que aún no puede buscar en internet. | Explicarlo con el LLM local, sin internet: es conocimiento general. | Probablemente «explícame» o «qué es» acaba en la negativa de búsqueda web en vez de en una pregunta al LLM. Revisar el router y las negativas fijas (`refusal`). |
| 2026-11-10 | «Elimina la carpeta llamada "carpeta nueva" del escritorio» | Dice que no hay ningún archivo así. | Encontrar la carpeta (en Windows suele llamarse «Nueva carpeta») y pedir confirmación para moverla a la papelera. | Revisar cómo se extrae el nombre con «llamada» y comillas, y si la búsqueda difusa tolera el orden de las palabras. Si no existe, sugerir la más parecida (SPEC sección 14). |
| 2026-11-11 | Arrancar Nyx en el portátil (Radeon integrada + RTX 3070 Laptop) | «Servicios listos» a los 23,3 s (sin Whisper, 6,5–7,9 s). whisper-server arranca primero en la integrada (dispositivo Vulkan 0, 4,2 s), se relanza en la RTX (1,6 s) y la transcripción de calentamiento tarda ~17 s. Además, `scripts/check_whisper.py` no elige tarjeta: en la integrada devuelve «!!!!…» y tarda ~10 s por frase. | Arranque en < 10 s (SPEC 14) y el script midiendo en la dedicada. | Elegir el dispositivo antes del primer arranque (p. ej. con `GGML_VK_VISIBLE_DEVICES` o leyendo la lista de `--list-devices` si existe) en `WhisperServer.start` y en `check_whisper.py`. Medir un segundo arranque: los ~17 s pueden ser la compilación de shaders de Vulkan de la primera vez (el controlador la guarda). |

## Corregidos

| Fecha | Error | Commit |
| --- | --- | --- |
| 2026-11-11 | El whisper-server.exe compilado en el sobremesa se caía en el portátil (0xC000001D en `ggml-cpu.dll`: AVX-512 que el Ryzen 7 6800H no tiene). Recompilado sin `GGML_NATIVE`, con `GGML_BACKEND_DL` y `GGML_CPU_ALL_VARIANTS` (`docs/benchmarks/README.md`). | Sin cambios de código |
| 2026-11-10 | El campo de texto aparecía encima de Nyx (y podía tapar un panel). | «5d: correcciones tras probar el asistente» |
| 2026-11-10 | Con dos monitores, el campo de texto salía en el último monitor donde se vio Nyx aunque el ratón estuviera en otro. | «5d: correcciones tras probar el asistente» |
| 2026-11-10 | El panel de respuesta subía encima de Nyx antes de que la forma terminara de irse (respuestas rápidas como «te quier» → «aún no sé hacer eso»). | `9dc7ed1` |
