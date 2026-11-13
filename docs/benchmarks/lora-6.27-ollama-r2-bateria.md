# Batería de frases · 2026-11-13 16:30

Modelo: `nyx-r2:7b`. Frases: 409. **Acierto: 391/409 (96 %)**.

Herramientas: todas (caben en su parte del contexto). Semilla del modelo: 1.

Primer token en lo que pasa por el LLM (primera pasada): mediana **468 ms**, media **497 ms**, peor 1359 ms.

| Camino | Frases | Acierto | Latencia mediana | Peor |
| --- | --- | --- | --- | --- |
| negativa | 7 | 7/7 | 0 ms | 0 ms |
| router | 267 | 267/267 | 0 ms | 5 ms |
| llm | 135 | 117/135 | 579 ms | 2105 ms |

## Fallos

| Frase | Camino | Qué hizo | Por qué |
| --- | --- | --- | --- |
| entra en mi correo de Gmail | llm | «Aún no sé abrirte el correo. Puedo abrirte Gmail o el Panel de control. ¿Te sirve?» | no ha actuado |
| está muy alto el sonido | llm | «Puedo bajarte el volumen. ¿A qué app quieres que lo haga?» | no ha actuado |
| no encuentro el Excel del presupuesto | llm | «Puedo abrirte Excel. ¿Quieres que lo haga?» | no ha actuado |
| pasa las capturas del escritorio a Imágenes | llm | move_files({"destination": "Imágenes"}) | llamada no válida (move_files: Field required; en Nyx se reintentaría) (1/3) |
| ya no quiero las capturas del escritorio, quítalas | llm | undo({}) | esperaba delete_files |
| a las 5 de la tarde tengo médico, avísame | llm | set_alarm({"time": "16:30"}) | time='16:30' (esperaba '17:00') |
| ya no hace falta que me despiertes mañana | llm | «Perfecto, no te despertaré. Si quieres, te pongo una para otra hora.» | no ha actuado |
| ¿cómo te llamo sin decir tu nombre? | llm | «Puedes llamarme Nyx.» | no ha actuado |
| ¿guardas lo que te digo? | llm | «Aún no sé guardar archivos. Si quieres, te abro el Bloc de notas y lo escribes tú.» | no ha actuado |
| ¿qué haces cuando estoy jugando? | llm | nyx_control({"setting": "modo partida", "value": "solo voz"}) | esperaba nyx_info |
| mientras juego no pienses, solo obedece órdenes | llm | nyx_control({"setting": "modo partida", "value": "solo voz"}) | setting='modo partida' (esperaba 'cerebro en partida') |
| pásame al inglés el texto que he copiado | llm | «Aún no sé copiar ni pegar. Puedo abrirte la app para que lo hagas tú.» | no ha actuado |
| ábreme una pestaña de incógnito en Chrome | llm | app_action({"action": "new_incognito_window", "app": "Google Chrome"}) | llamada no válida (app_action: Value error, acción desconocida; usa una de: answer_call, back, bookmark, close_tab, command_palette, downloads, find, forward, fullscreen, history, incognito, like, mark_read, new_tab, new_window, next_tab, previous_tab, print, quick_open, quick_switcher, reload, reopen_tab, repeat, save, save_as, search, shuffle, toggle_deafen, toggle_mute, toggle_sidebar, up, volume_down, volume_up, zoom_in, zoom_out, zoom_reset; en Nyx se reintentaría) (1/3) |
| silencia el Discord y sube la música | llm | set_volume({"app": "discord", "mute": true, "music": true}) | llamada no válida (set_volume: Extra inputs are not permitted; en Nyx se reintentaría) (1/3) |
| apaga el wifi y bloquea el ordenador | llm | system_power({"action": "lock"}); toggle_wifi({"enabled": false}) | plan distinto: ['system_power', 'toggle_wifi'] |
| ¿qué dirección IP tiene mi ordenador? | llm | system_info({"what": "ip"}) | llamada no válida (system_info: Input should be 'battery', 'cpu', 'ram', 'disk' or 'top'; en Nyx se reintentaría) |
| ¿cuánto tiempo lleva encendido el PC? | llm | system_info({"what": "top"}) | esperaba run_powershell |
| ¿qué versión de Windows tengo? | llm | «Windows 11 es la versión más reciente que tienes.» | no ha actuado |
