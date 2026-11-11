# Errores conocidos

Fallos vistos al usar Nyx que quedan pendientes de corregir. Se apuntan aquí para no perderlos y se corrigen por tandas sin parar el plan de fases. Al corregir uno, se mueve a «Corregidos» con la fecha y el commit, y se añade su frase a la batería de pruebas (`core/tests`).

## Pendientes

| Fecha | Frase o situación | Qué pasa | Qué debería pasar | Pista |
| --- | --- | --- | --- | --- |
| 2026-11-10 | «Explícame qué es un agujero negro» (escrito, portátil) | Responde que aún no puede buscar en internet. | Explicarlo con el LLM local, sin internet: es conocimiento general. | Probablemente «explícame» o «qué es» acaba en la negativa de búsqueda web en vez de en una pregunta al LLM. Revisar el router y las negativas fijas (`refusal`). |
| 2026-11-10 | «Elimina la carpeta llamada "carpeta nueva" del escritorio» | Dice que no hay ningún archivo así. | Encontrar la carpeta (en Windows suele llamarse «Nueva carpeta») y pedir confirmación para moverla a la papelera. | Revisar cómo se extrae el nombre con «llamada» y comillas, y si la búsqueda difusa tolera el orden de las palabras. Si no existe, sugerir la más parecida (SPEC sección 14). |
| 2026-11-11 | «Bájate la calidad del cristal al mínimo» (en partida) | `app_action zoom_out` ×3 sobre Rocket League (bloqueado por la partida). | Cambiar `appearance.glass.quality` a «bajo». | Falta `nyx_control` (fase 6). |
| 2026-11-11 | «Cierra la carpeta que tengo abierta» / «Cierra la carpeta llamada nueva carpeta» | «No veo la carpeta … abierto». | Cerrar esa ventana del Explorador. | `close_app` no conoce las ventanas del Explorador por carpeta. |
| 2026-11-11 | «Busca qué aplicaciones ha creado Tepnyx» | Busca archivos en el disco. | Buscar en internet. | Falta `web_search` (fase 6); el router no debe mandar preguntas a `find_files`. |
| 2026-11-11 | Arrancar Nyx en el portátil (Radeon integrada + RTX 3070 Laptop) | «Servicios listos» a los 23,3 s (sin Whisper, 6,5–7,9 s). whisper-server arranca primero en la integrada (dispositivo Vulkan 0, 4,2 s), se relanza en la RTX (1,6 s) y la transcripción de calentamiento tarda ~17 s. Además, `scripts/check_whisper.py` no elige tarjeta: en la integrada devuelve «!!!!…» y tarda ~10 s por frase. | Arranque en < 10 s (SPEC 14) y el script midiendo en la dedicada. | Elegir el dispositivo antes del primer arranque (p. ej. con `GGML_VK_VISIBLE_DEVICES` o leyendo la lista de `--list-devices` si existe) en `WhisperServer.start` y en `check_whisper.py`. Medir un segundo arranque: los ~17 s pueden ser la compilación de shaders de Vulkan de la primera vez (el controlador la guarda). |

## Corregidos

| Fecha | Error | Commit |
| --- | --- | --- |
| 2026-11-11 | Nombres de herramientas en la burbuja y en la voz («[set_alarm | establece una alarma]», «listalarms, dices las alarmas»), y «alarma que suene en 10 segundos» a las 00:10. | «Tras probar la 6.03» |
| 2026-11-11 | «¿Cuánto le queda a la alarma?» → «no hay ninguna» (había una): `list_alarms` y regla de no decir cómo está el PC sin mirarlo. | 0.6 (6.03) |
| 2026-11-11 | «Explícame tu configuración para el modo partida» abría Ajustes: ahora `nyx_info` lo explica desde `brain/knowledge/nyx.md`. | 0.6 (6.03) |
| 2026-11-11 | «Ábrela» tras crear una carpeta no sabía qué abrir: ahora lo último hecho (con su ruta) va como contexto y el router deja las referencias al modelo. | 0.6 (6.02) |
| 2026-11-11 | La burbuja y la voz repetían lo mismo («10 archivos en Descargas, hay 10 archivos en Descargas»): si la línea secundaria dice lo mismo que el dato, se quita. | «Tras probar la 6.01» |
| 2026-11-11 | «¿Qué hay en Descargas?» decía «10 archivos» con cientos dentro: ahora dice el total de archivos y carpetas y los 10 más recientes. | «Tras probar la 6.01» |
| 2026-11-11 | En la ventana de seguimiento ignoraba correcciones («Pero hay muchos más»): el clasificador las cuenta como dirigidas a Nyx y, ante la duda, también. | «Tras probar la 6.01» |
| 2026-11-11 | «Búscame la última factura que tengo» buscaba un archivo llamado así: ahora busca «factura», la más reciente, y si no hay dice «No he encontrado ninguna factura». | «Tras probar la 6.01» |
| 2026-11-11 | Ajustes, abierta desde la cola de la partida, salía sin fondo de cristal: el motor la daba por tapada por un overlay «siempre encima» del juego. Ahora esas ventanas no cuentan (confirmado por el usuario). | `ede328a` |
| 2026-11-11 | Tirones en Rocket League cuando Nyx pensaba con el 14B (no cabe junto al juego: −80 % de FPS). En partida, el 7B en la gráfica (−3,4 %, sin tirones) o sin cerebro si no cabe. | 0.5, bloque 4 (pendiente de probar) |
| 2026-11-11 | «Pon música» le daba al play al vídeo de YouTube que estaba abierto. Ahora va a Spotify si está instalada; en la 0.6, a la app donde el usuario suela escuchar música. | 0.5 (pendiente de probar) |
| 2026-11-11 | En partida, «muéstrame los FPS…» se dejaba para después como `focus_window` y fallaba al terminar (parecía que solo hacía la última). Ahora se comprueba antes de diferir, la cola se guarda en disco, se puede ver y cancelar («¿qué tienes pendiente?») y el resumen final se dice en voz. | 0.5, bloque 2 (pendiente de probar) |
| 2026-11-11 | Leía en voz alta `appaction({…}); appaction({…})`. En partida, «salta», «acelera»… tienen negativa fija; un plan bloqueado por la partida no se reintenta; el intérprete entiende varias llamadas en una línea y nunca se dice ni se muestra código. | 0.5, bloque 1 (pendiente de probar) |
| 2026-11-11 | «Ábrela» abría Aimlabs: con menos de 3 letras ya no se busca de forma difusa. (Que «ábrela» abra lo recién creado llega con la memoria corta de la 0.6.) | 0.5, bloque 2 (pendiente de probar) |
| 2026-11-11 | El whisper-server.exe compilado en el sobremesa se caía en el portátil (0xC000001D en `ggml-cpu.dll`: AVX-512 que el Ryzen 7 6800H no tiene). Recompilado sin `GGML_NATIVE`, con `GGML_BACKEND_DL` y `GGML_CPU_ALL_VARIANTS` (`docs/benchmarks/README.md`). | Sin cambios de código |
| 2026-11-10 | El campo de texto aparecía encima de Nyx (y podía tapar un panel). | «5d: correcciones tras probar el asistente» |
| 2026-11-10 | Con dos monitores, el campo de texto salía en el último monitor donde se vio Nyx aunque el ratón estuviera en otro. | «5d: correcciones tras probar el asistente» |
| 2026-11-10 | El panel de respuesta subía encima de Nyx antes de que la forma terminara de irse (respuestas rápidas como «te quier» → «aún no sé hacer eso»). | `9dc7ed1` |
