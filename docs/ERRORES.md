# Errores conocidos

Fallos vistos al usar Nyx que quedan pendientes de corregir. Se apuntan aquí para no perderlos y se corrigen por tandas sin parar el plan de fases. Al corregir uno, se mueve a «Corregidos» con la fecha y el commit, y se añade su frase a la batería de pruebas (`core/tests`).

## Pendientes

| Fecha | Frase o situación | Qué pasa | Qué debería pasar | Pista |
| --- | --- | --- | --- | --- |
| 2026-11-10 | «Explícame qué es un agujero negro» (escrito, portátil) | Responde que aún no puede buscar en internet. | Explicarlo con el LLM local, sin internet: es conocimiento general. | Probablemente «explícame» o «qué es» acaba en la negativa de búsqueda web en vez de en una pregunta al LLM. Revisar el router y las negativas fijas (`refusal`). |
| 2026-11-10 | «Elimina la carpeta llamada "carpeta nueva" del escritorio» | Dice que no hay ningún archivo así. | Encontrar la carpeta (en Windows suele llamarse «Nueva carpeta») y pedir confirmación para moverla a la papelera. | Revisar cómo se extrae el nombre con «llamada» y comillas, y si la búsqueda difusa tolera el orden de las palabras. Si no existe, sugerir la más parecida (SPEC sección 14). |
| 2026-11-11 | Portátil (Ryzen 7 6800H) con el whisper-server.exe compilado en el sobremesa (Ryzen 7 7700X) | Ajustes dice que whisper está instalado, pero no se transcribe nada: Nyx no aparece al llamarlo. En el registro, «whisper-server terminó al arrancar» justo después de «using Vulkan0 backend», en la Radeon integrada y también en la RTX. Código de salida 0xC000001D (instrucción no válida) en `ggml-cpu.dll`. | Que whisper-server funcione en cualquier procesador compatible y que Nyx explique en una frase por qué no hay voz. | whisper.cpp se compila por defecto con `GGML_NATIVE=ON`: usa las instrucciones del procesador donde se compila (AVX-512 del Zen 4), que el 6800H no tiene. No es un fallo del código de Nyx, sino de cómo se compila. Recompilar con `-DGGML_NATIVE=OFF -DGGML_BACKEND_DL=ON -DGGML_CPU_ALL_VARIANTS=ON` (una variante de `ggml-cpu` por familia de procesador, elegida al arrancar); así hay que compilar también lo que se distribuya con el instalador. Queda por ver si, una vez arreglado, arrancar primero en la Radeon integrada (dispositivo 0) da problemas antes de que `pick_device` relance en la dedicada. |

## Corregidos

| Fecha | Error | Commit |
| --- | --- | --- |
| 2026-11-10 | El campo de texto aparecía encima de Nyx (y podía tapar un panel). | «5d: correcciones tras probar el asistente» |
| 2026-11-10 | Con dos monitores, el campo de texto salía en el último monitor donde se vio Nyx aunque el ratón estuviera en otro. | «5d: correcciones tras probar el asistente» |
| 2026-11-10 | El panel de respuesta subía encima de Nyx antes de que la forma terminara de irse (respuestas rápidas como «te quier» → «aún no sé hacer eso»). | `9dc7ed1` |
