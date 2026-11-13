# Batería de frases · 2026-11-13 16:17

Modelo: `nyx-r1:7b`. Frases: 80. **Acierto: 70/80 (88 %)**.

Herramientas: todas (caben en su parte del contexto). Semilla del modelo: 1.

Primer token en lo que pasa por el LLM (primera pasada): mediana **617 ms**, media **627 ms**, peor 989 ms.

| Camino | Frases | Acierto | Latencia mediana | Peor |
| --- | --- | --- | --- | --- |
| router | 25 | 25/25 | 0 ms | 2 ms |
| llm | 55 | 45/55 | 638 ms | 1584 ms |

## Fallos

| Frase | Camino | Qué hizo | Por qué |
| --- | --- | --- | --- |
| ponme el Discord, porfa | llm | focus_window({"name": "discord"}) | esperaba open_app |
| pásame a la ventana del Chrome | llm | window_layout({"name": "chrome", "action": "next_monitor"}) | esperaba focus_window |
| quita el Discord de la vista | llm | close_app({"name": "discord"}) | esperaba window_layout |
| para la canción un momento | llm | now_playing({}) | esperaba media_control |
| esta no me gusta, la siguiente | llm | open_nyx_settings({"section": "general"}) | esperaba media_control |
| despiértame pasado mañana a las ocho menos cuarto | llm | set_alarm({"time": "08:15", "repeat": "weekdays"}) | time='08:15' (esperaba '07:45') |
| ¿qué alarmas tengo puestas para mañana? | llm | list_alarms({"day": "tomorrow"}) | llamada no válida (list_alarms: Extra inputs are not permitted; en Nyx se reintentaría) |
| conéctate al wifi otra vez | llm | toggle_wifi({}) | enabled=None (esperaba True) |
| copia esto: nos vemos a las cinco | llm | type_text({"text": "nos vemos a las cinco"}) | esperaba clipboard |
| gracias, Nyx | llm | pending({"action": "list"}) | ha actuado |
