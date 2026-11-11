# Errores conocidos

Fallos vistos al usar Nyx que quedan pendientes de corregir. Se apuntan aquí para no perderlos y se corrigen por tandas sin parar el plan de fases. Al corregir uno, se mueve a «Corregidos» con la fecha y el commit, y se añade su frase a la batería de pruebas (`core/tests`).

## Pendientes

| Fecha | Frase o situación | Qué pasa | Qué debería pasar | Pista |
| --- | --- | --- | --- | --- |
| 2026-11-10 | «Explícame qué es un agujero negro» (escrito, portátil) | Responde que aún no puede buscar en internet. | Explicarlo con el LLM local, sin internet: es conocimiento general. | Probablemente «explícame» o «qué es» acaba en la negativa de búsqueda web en vez de en una pregunta al LLM. Revisar el router y las negativas fijas (`refusal`). |
| 2026-11-10 | «Elimina la carpeta llamada "carpeta nueva" del escritorio» | Dice que no hay ningún archivo así. | Encontrar la carpeta (en Windows suele llamarse «Nueva carpeta») y pedir confirmación para moverla a la papelera. | Revisar cómo se extrae el nombre con «llamada» y comillas, y si la búsqueda difusa tolera el orden de las palabras. Si no existe, sugerir la más parecida (SPEC sección 14). |
| 2026-11-11 | Jugando a Rocket League con `qwen2.5:14b`, cada vez que Nyx piensa | El juego va a tirones. Latencia de 2 a 19 s hasta la voz. | Ningún tirón; en partida, Nyx usa un cerebro que quepa junto al juego. | 14B (~9 GB) + Whisper + el juego superan los 12 GB de VRAM, y el LLM ocupa la GPU al 100 % mientras genera. Ver HOJA-DE-RUTA §1.1. |
| 2026-11-11 | «Muéstrame los FPS en el Rocket League» y «Abre la configuración de Nyx» en partida | Al terminar parece que solo hace la última. | Hacer las dos o decir al momento que la primera no tiene sentido. | Se ejecutaron las dos: la regla `focus` del router convirtió la primera en `focus_window("los fps en el rocket league")`, que falló al terminar. Comprobar antes de diferir. HOJA-DE-RUTA §1.3. |
| 2026-11-11 | «Quiero que saltes y tires hacia adelante el coche» (en partida) | Lee en voz alta `appaction({"app": "Rocket League", "action": "jump"}); …`. | Negativa fija: «Dentro de los juegos no hago nada». | El reintento tras el plan no válido devolvió dos llamadas escritas con «;» tras la cabecera `[acciones]` y `textcalls.py` no las reconoció. Falta un filtro que nunca diga código. HOJA-DE-RUTA §1.4. |
| 2026-11-11 | «Bájate la calidad del cristal al mínimo» (en partida) | `app_action zoom_out` ×3 sobre Rocket League (bloqueado por la partida). | Cambiar `appearance.glass.quality` a «bajo». | Falta `nyx_control` (fase 6). |
| 2026-11-11 | «¿Cuánto le queda a la alarma?» | «No hay ninguna alarma programada actualmente» (había una). | Decir cuánto le queda. | Falta `list_alarms` y la regla de no afirmar nada del PC sin una herramienta. |
| 2026-11-11 | «Ábrela» justo después de crear «Nueva carpeta» | Abre Aimlabs. | Abrir la carpeta recién creada. | El router buscó «la» de forma difusa. No buscar nombres de menos de 3 letras y meter lo creado en la memoria corta. |
| 2026-11-11 | «Cierra la carpeta que tengo abierta» / «Cierra la carpeta llamada nueva carpeta» | «No veo la carpeta … abierto». | Cerrar esa ventana del Explorador. | `close_app` no conoce las ventanas del Explorador por carpeta. |
| 2026-11-11 | «Busca qué aplicaciones ha creado Tepnyx» | Busca archivos en el disco. | Buscar en internet. | Falta `web_search` (fase 6); el router no debe mandar preguntas a `find_files`. |
| 2026-11-11 | «Explícame tu configuración para el modo partida» | Abre Ajustes. | Explicarla con voz y burbuja. | Nyx no se conoce a sí misma (HOJA-DE-RUTA §3.7). |
| 2026-11-11 | Arrancar Nyx en el portátil (Radeon integrada + RTX 3070 Laptop) | «Servicios listos» a los 23,3 s (sin Whisper, 6,5–7,9 s). whisper-server arranca primero en la integrada (dispositivo Vulkan 0, 4,2 s), se relanza en la RTX (1,6 s) y la transcripción de calentamiento tarda ~17 s. Además, `scripts/check_whisper.py` no elige tarjeta: en la integrada devuelve «!!!!…» y tarda ~10 s por frase. | Arranque en < 10 s (SPEC 14) y el script midiendo en la dedicada. | Elegir el dispositivo antes del primer arranque (p. ej. con `GGML_VK_VISIBLE_DEVICES` o leyendo la lista de `--list-devices` si existe) en `WhisperServer.start` y en `check_whisper.py`. Medir un segundo arranque: los ~17 s pueden ser la compilación de shaders de Vulkan de la primera vez (el controlador la guarda). |

## Corregidos

| Fecha | Error | Commit |
| --- | --- | --- |
| 2026-11-11 | El whisper-server.exe compilado en el sobremesa se caía en el portátil (0xC000001D en `ggml-cpu.dll`: AVX-512 que el Ryzen 7 6800H no tiene). Recompilado sin `GGML_NATIVE`, con `GGML_BACKEND_DL` y `GGML_CPU_ALL_VARIANTS` (`docs/benchmarks/README.md`). | Sin cambios de código |
| 2026-11-10 | El campo de texto aparecía encima de Nyx (y podía tapar un panel). | «5d: correcciones tras probar el asistente» |
| 2026-11-10 | Con dos monitores, el campo de texto salía en el último monitor donde se vio Nyx aunque el ratón estuviera en otro. | «5d: correcciones tras probar el asistente» |
| 2026-11-10 | El panel de respuesta subía encima de Nyx antes de que la forma terminara de irse (respuestas rápidas como «te quier» → «aún no sé hacer eso»). | `9dc7ed1` |
