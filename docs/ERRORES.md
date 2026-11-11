# Errores conocidos

Fallos vistos al usar Nyx que quedan pendientes de corregir. Se apuntan aquí para no perderlos y se corrigen por tandas sin parar el plan de fases. Al corregir uno, se mueve a «Corregidos» con la fecha y el commit, y se añade su frase a la batería de pruebas (`core/tests`).

## Pendientes

| Fecha | Frase o situación | Qué pasa | Qué debería pasar | Pista |
| --- | --- | --- | --- | --- |
| 2026-11-10 | «Explícame qué es un agujero negro» (escrito, portátil) | Responde que aún no puede buscar en internet. | Explicarlo con el LLM local, sin internet: es conocimiento general. | Probablemente «explícame» o «qué es» acaba en la negativa de búsqueda web en vez de en una pregunta al LLM. Revisar el router y las negativas fijas (`refusal`). |
| 2026-11-10 | «Elimina la carpeta llamada "carpeta nueva" del escritorio» | Dice que no hay ningún archivo así. | Encontrar la carpeta (en Windows suele llamarse «Nueva carpeta») y pedir confirmación para moverla a la papelera. | Revisar cómo se extrae el nombre con «llamada» y comillas, y si la búsqueda difusa tolera el orden de las palabras. Si no existe, sugerir la más parecida (SPEC sección 14). |
| 2026-11-11 | Portátil con dos gráficas (Radeon integrada + RTX 3070 Laptop): llamar a Nyx por voz | Ajustes dice que whisper está instalado, pero no se transcribe nada: Nyx no aparece al llamarlo. En el registro, «whisper-server terminó al arrancar» justo después de «using Vulkan0 backend». También pasa con `scripts/check_whisper.py`. | Arrancar whisper-server en la RTX y transcribir. | whisper.cpp numera la Radeon integrada como dispositivo 0. `WhisperServer.start` lanza primero sin `--device` (usa la 0), y como el proceso se cae no llega a `pick_device` ni a relanzar en la dedicada. Opciones: elegir el dispositivo antes del primer arranque o, si se cae, leer la lista de tarjetas de su salida y relanzar con la dedicada. `check_whisper.py` necesita lo mismo. Mientras tanto: `GGML_VK_VISIBLE_DEVICES=1`. |

## Corregidos

| Fecha | Error | Commit |
| --- | --- | --- |
| 2026-11-10 | El campo de texto aparecía encima de Nyx (y podía tapar un panel). | «5d: correcciones tras probar el asistente» |
| 2026-11-10 | Con dos monitores, el campo de texto salía en el último monitor donde se vio Nyx aunque el ratón estuviera en otro. | «5d: correcciones tras probar el asistente» |
| 2026-11-10 | El panel de respuesta subía encima de Nyx antes de que la forma terminara de irse (respuestas rápidas como «te quier» → «aún no sé hacer eso»). | `9dc7ed1` |
