# Batería de frases · 2026-11-13 03:05

Modelo: `qwen2.5:7b`. Frases: 80. **Acierto: 58/80 (72 %)**.

Herramientas: todas (caben en su parte del contexto). Semilla del modelo: 1.

Primer token en lo que pasa por el LLM (primera pasada): mediana **347 ms**, media **330 ms**, peor 705 ms.

| Camino | Frases | Acierto | Latencia mediana | Peor |
| --- | --- | --- | --- | --- |
| router | 23 | 21/23 | 0 ms | 2 ms |
| llm | 57 | 37/57 | 366 ms | 888 ms |

## Fallos

| Frase | Camino | Qué hizo | Por qué |
| --- | --- | --- | --- |
| trae el Spotify delante | llm | «tronca el Spotify» | no ha actuado |
| el Chrome que ocupe toda la pantalla | llm | focus_window({"name": "Chrome"}) | esperaba window_layout/app_action |
| quita el Discord de la vista | llm | close_app({"name": "Discord"}) | esperaba window_layout |
| echa el Chrome a la derecha | llm | focus_window({"name": "Chrome"}) | esperaba window_layout |
| súbelo, que casi no se oye | llm | «sube el volumen, aumenta el sonido» | no ha actuado (1/3) |
| quita el sonido del todo | llm | set_volume({"level": 0, "app": null}) | mute=None (esperaba True) (1/3) |
| para la canción un momento | llm | «¿Qué canción quieres reproducir?» | no ha actuado |
| esta no me gusta, la siguiente | llm | «13, hoy es un día especial» | no ha actuado |
| dale otra vez a la música | llm | «repite la canción» | no ha actuado (1/3) |
| despiértame pasado mañana a las ocho menos cuarto | llm | set_alarm({"label": "Despertar", "time": "08:24", "day": "tomorrow"}) | time='08:24' (esperaba '07:45') |
| las galletas tienen que estar 15 minutos en el horno, avísame | llm | «Pon una alarma para dentro de 15 minutos.» | no ha actuado |
| ¿qué alarmas tengo puestas para mañana? | llm | «Veamos si tienes alguna alarma para el sábado 14 de noviembre.» | no ha actuado |
| ¿el portátil se está cargando? | llm | «No puedo verificar si el portátil se está cargando sin usar una herramienta específica. ¿Quieres que revise el estado d | no ha actuado |
| ¿cuánta RAM estoy gastando ahora mismo? | llm | «Estás usando aproximadamente el 30% del CPU, lo que indica que no estás utilizando mucho la RAM en este momento.» | no ha actuado (1/3) |
| ¿tengo hueco en el disco para otro juego? | llm | «Para saber si tienes hueco para otro juego, necesito ver cuánto espacio libre tienes. Vamos a comprobarlo.» | no ha actuado |
| ¿qué tiempo va a hacer el fin de semana? | llm | «Para saber el tiempo del fin de semana, necesito saber en qué ciudad te encuentras. ¿Podrías decírmela?» | no ha actuado |
| conéctate al wifi otra vez | llm | toggle_wifi({"enabled": null}) | enabled=None (esperaba True) |
| enséñame lo último que me he bajado | llm | find_files({"folder": "Descargas", "newest": 1}) | llamada no válida (find_files: Value error, falta query (parte del nombre) o extension; en Nyx se reintentaría) (1/3) |
| ábreme la carpeta de Descargas | router | open_path({"target": "C:\\Users\\usuario\\Downloads"}) | target='C:\\Users\\usuario\\Downloads' (esperaba 'Descargas') |
| quiero cambiar el idioma del teclado | llm | «Aún no sé cómo cambiar el idioma del teclado desde aquí.» | no ha actuado |
| copia esto: nos vemos a las cinco | llm | type_text({"app": null, "text": "nos vemos a las cinco"}) | esperaba clipboard |
| abre el bloc de notas y escribe la lista de la compra | router | open_app({"name": "Bloc de notas"}); type_text({"text": "la lista de la compra"}) | plan distinto: ['open_app', 'type_text'] |

## Notas (6.27: referencia antes del LoRA)

`tests/battery/reserva.jsonl`: 80 frases nuevas escritas el 2026-11-13, antes de generar ningún
ejemplo de entrenamiento, que **nunca** se usan para entrenar (como la batería). Con qwen2.5:7b
sin ajustar y semilla 1: **58/80**, LLM 37/57. Tras medir se corrigieron dos expectativas que
estaban mal escritas (no fallos de Nyx): «ábreme la carpeta de Descargas» abre la ruta real (se
espera `open_path` sin fijar el texto) y el plan «abre el bloc de notas y escribe…» de las reglas
no lleva la espera (la añade quien ejecuta). Con ellas, la referencia queda en 60/80.
