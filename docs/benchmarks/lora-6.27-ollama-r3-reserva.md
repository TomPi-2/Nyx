# Batería de frases · 2026-11-13 21:07

Modelo: `nyx-r3:7b`. Frases: 80. **Acierto: 73/80 (91 %)**.

Herramientas: todas (caben en su parte del contexto). Semilla del modelo: 1.

Primer token en lo que pasa por el LLM (primera pasada): mediana **348 ms**, media **351 ms**, peor 548 ms.

| Camino | Frases | Acierto | Latencia mediana | Peor |
| --- | --- | --- | --- | --- |
| router | 25 | 25/25 | 0 ms | 2 ms |
| llm | 55 | 48/55 | 360 ms | 950 ms |

## Fallos

| Frase | Camino | Qué hizo | Por qué |
| --- | --- | --- | --- |
| pásame a la ventana del Chrome | llm | window_layout({"name": "Chrome", "action": "next_monitor"}) | esperaba focus_window |
| despiértame pasado mañana a las ocho menos cuarto | llm | set_alarm({"repeat": "none", "time": "08:24", "day": "tomorrow"}) | time='08:24' (esperaba '07:45') |
| ¿qué alarmas tengo puestas para mañana? | llm | list_alarms({"day": "tomorrow"}) | llamada no válida (list_alarms: Extra inputs are not permitted; en Nyx se reintentaría) |
| conéctate al wifi otra vez | llm | toggle_wifi({}) | enabled=None (esperaba True) |
| quiero cambiar el idioma del teclado | llm | «Aún no sé cambiar idiomas. Puedo abrirte la Configuración para que lo hagas tú.» | no ha actuado |
| copia esto: nos vemos a las cinco | llm | type_text({"app": "Bloc de notas", "text": "nos vemos a las cinco"}) | esperaba clipboard |
| dame una idea para cenar | llm | «Aún no sé buscar en internet. Puedo abrirte el navegador y que lo busques tú.» | sin respuesta útil (1/3) |
