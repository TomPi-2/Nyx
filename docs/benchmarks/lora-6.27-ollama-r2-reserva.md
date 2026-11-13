# Batería de frases · 2026-11-13 16:25

Modelo: `nyx-r2:7b`. Frases: 80. **Acierto: 70/80 (88 %)**.

Herramientas: todas (caben en su parte del contexto). Semilla del modelo: 1.

Primer token en lo que pasa por el LLM (primera pasada): mediana **440 ms**, media **436 ms**, peor 742 ms.

| Camino | Frases | Acierto | Latencia mediana | Peor |
| --- | --- | --- | --- | --- |
| router | 25 | 25/25 | 0 ms | 2 ms |
| llm | 55 | 45/55 | 462 ms | 1164 ms |

## Fallos

| Frase | Camino | Qué hizo | Por qué |
| --- | --- | --- | --- |
| ponme el Discord, porfa | llm | focus_window({"name": "discord"}) | esperaba open_app |
| pásame a la ventana del Chrome | llm | window_layout({"name": "chrome", "action": "maximize"}) | esperaba focus_window |
| quita el Discord de la vista | llm | close_app({"name": "discord"}) | esperaba window_layout |
| esta no me gusta, la siguiente | llm | pending({"action": "list"}) | esperaba media_control |
| despiértame pasado mañana a las ocho menos cuarto | llm | set_alarm({"time": "08:25", "day": "tomorrow"}) | time='08:25' (esperaba '07:45') |
| ¿qué alarmas tengo puestas para mañana? | llm | list_alarms({"day": "tomorrow"}) | llamada no válida (list_alarms: Extra inputs are not permitted; en Nyx se reintentaría) |
| conéctate al wifi otra vez | llm | «Aún no puedo hacer eso desde aquí. Si quieres, te lo abro en el PC y lo haces tú.» | no ha actuado |
| mueve las fotos del escritorio a Imágenes | llm | move_files({"kind": "images", "names": ["fotos"], "destination": "Imágenes", "extension": "jpg"}) | llamada no válida (move_files: Field required; en Nyx se reintentaría) (1/3) |
| quiero cambiar el idioma del teclado | llm | «Aún no sé cambiar el idioma del teclado. Puedo abrirte la Configuración y te ayudo desde allí.» | no ha actuado |
| copia esto: nos vemos a las cinco | llm | type_text({"app": null, "text": "nos vemos a las cinco"}) | esperaba clipboard |
