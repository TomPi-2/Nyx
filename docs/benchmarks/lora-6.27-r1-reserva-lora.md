# Batería de frases · 2026-11-13 09:44

Modelo: `lora`. Frases: 80. **Acierto: 72/80 (90 %)**.

Herramientas: todas (caben en su parte del contexto). Semilla del modelo: 1.

Primer token en lo que pasa por el LLM (primera pasada): mediana **7276 ms**, media **7939 ms**, peor 19533 ms.

| Camino | Frases | Acierto | Latencia mediana | Peor |
| --- | --- | --- | --- | --- |
| router | 25 | 25/25 | 0 ms | 2 ms |
| llm | 55 | 47/55 | 7279 ms | 19533 ms |

## Fallos

| Frase | Camino | Qué hizo | Por qué |
| --- | --- | --- | --- |
| quita el Discord de la vista | llm | close_app({"name": "discord"}) | esperaba window_layout |
| para la canción un momento | llm | «<toolcall> {"name": "now user (Ahora es viernes 13 de noviembre de 2026, 09:26.) para la canción un momento» | no ha actuado |
| esta no me gusta, la siguiente | llm | open_nyx_settings({"section": "general"}) | esperaba media_control |
| ¿quién canta esto que está sonando? | llm | «<toolcall> {"name": "now assistant <toolcall> {"name": "now assistant <toolcall> {"name": "now assistant <toolcall> {"n | no ha actuado |
| despiértame pasado mañana a las ocho menos cuarto | llm | set_alarm({"time": "08:01", "day": "tomorrow"}) | time='08:01' (esperaba '07:45') |
| conéctate al wifi otra vez | llm | toggle_wifi({}) | enabled=None (esperaba True) |
| enséñame lo último que me he bajado | llm | list_files({"folder": "descargas", "newer": 1}) | llamada no válida (list_files: Extra inputs are not permitted; en Nyx se reintentaría) (1/3) |
| gracias, Nyx | llm | undo({}) | ha actuado |
