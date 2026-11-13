# Batería de frases · 2026-11-13 16:06

Modelo: `qwen2.5:7b`. Frases: 80. **Acierto: 62/80 (78 %)**.

Herramientas: todas (caben en su parte del contexto). Semilla del modelo: 1.

Primer token en lo que pasa por el LLM (primera pasada): mediana **581 ms**, media **741 ms**, peor 1930 ms.

| Camino | Frases | Acierto | Latencia mediana | Peor |
| --- | --- | --- | --- | --- |
| router | 25 | 25/25 | 0 ms | 2 ms |
| llm | 55 | 37/55 | 869 ms | 3789 ms |

## Fallos

| Frase | Camino | Qué hizo | Por qué |
| --- | --- | --- | --- |
| trae el Spotify delante | llm | «Traigo al frente Spotify.» | no ha actuado (1/3) |
| el Chrome que ocupe toda la pantalla | llm | focus_window({"name": "chrome"}); window_layout({"action": "maximize"}) | esperaba window_layout/app_action (1/3) |
| quita el Discord de la vista | llm | focus_window({"name": "chrome"}) | esperaba window_layout |
| echa el Chrome a la derecha | llm | «chromium al derecho» | no ha actuado |
| no quiero ver más el Discord, ciérralo | llm | «cimalo Discord.» | no ha actuado |
| para la canción un momento | llm | «-mediacontrol action=playpause» | no ha actuado |
| esta no me gusta, la siguiente | llm | «No entiendo el contexto de tu frase. ¿Podrías decirme qué no te gusta o qué quieres que haga a continuación?» | no ha actuado |
| dale otra vez a la música | llm | «mediacontrol {action: play}» | no ha actuado (1/3) |
| despiértame pasado mañana a las ocho menos cuarto | llm | set_alarm({"label": "Despertar", "time": "08:24", "day": "tomorrow"}) | time='08:24' (esperaba '07:45') |
| ¿qué alarmas tengo puestas para mañana? | llm | list_alarms({"day": "tomorrow"}) | llamada no válida (list_alarms: Extra inputs are not permitted; en Nyx se reintentaría) |
| ¿el portátil se está cargando? | llm | «consulta la batería {what=battery}.» | no ha actuado |
| ¿tengo hueco en el disco para otro juego? | llm | «consulta el espacio libre en el disco (disk)» | no ha actuado |
| ¿qué programa está tirando tanto del procesador? | llm | «echa un vistazo a lo que consume más CPU.» | no ha actuado |
| ¿cómo va de carga el procesador? | llm | «echa un vistazo al uso de la CPU.» | no ha actuado |
| ¿qué tiempo va a hacer el fin de semana? | llm | «Para saber el tiempo del fin de semana, necesito saber en qué ciudad estás. ¿Podrías decirme a qué ciudad te refieres?» | no ha actuado |
| conéctate al wifi otra vez | llm | toggle_wifi({}) | enabled=None (esperaba True) (1/3) |
| quiero cambiar el idioma del teclado | llm | «Lo siento, actualmente no puedo cambiar el idioma del teclado directamente desde Nyx. Aún no sé hacer eso.» | no ha actuado |
| copia esto: nos vemos a las cinco | llm | type_text({"app": null, "text": "nos vemos a las cinco"}) | esperaba clipboard |
