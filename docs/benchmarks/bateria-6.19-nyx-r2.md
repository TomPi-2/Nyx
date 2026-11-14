# Batería de frases · 2026-11-14 03:06

Modelo: `nyx-r2:7b`. Frases: 409. **Acierto: 389/409 (95 %)**.

Herramientas: todas (caben en su parte del contexto). Semilla del modelo: 1.

Primer token en lo que pasa por el LLM (primera pasada): mediana **360 ms**, media **388 ms**, peor 999 ms.

| Camino | Frases | Acierto | Latencia mediana | Peor |
| --- | --- | --- | --- | --- |
| negativa | 7 | 7/7 | 0 ms | 0 ms |
| router | 268 | 267/268 | 0 ms | 5 ms |
| llm | 134 | 115/134 | 430 ms | 1464 ms |

## Fallos

| Frase | Camino | Qué hizo | Por qué |
| --- | --- | --- | --- |
| entra en mi correo de Gmail | llm | open_app({"name": "Gmail"}) | esperaba open_url |
| está muy alto el sonido | llm | «Puedo bajarlo. ¿A qué nivel quieres que lo ponga?» | no ha actuado |
| ¿tengo algún PDF en el escritorio? | llm | find_files({"folder": "el escritorio", "kind": "documents"}) | llamada no válida (find_files: Value error, falta query (parte del nombre) o extension; en Nyx se reintentaría) (1/3) |
| no encuentro el Excel del presupuesto | llm | «Puedo abrirte Excel. ¿Quieres que lo haga?» | no ha actuado |
| lleva los PDF de Descargas a Documentos | llm | move_files({"folder": "descargas", "destination": "documentos", "kind": "documents"}) | extension=None (esperaba 'pdf') (1/3) |
| pasa las capturas del escritorio a Imágenes | llm | move_files({"destination": "Imágenes"}) | llamada no válida (move_files: Field required; en Nyx se reintentaría) (1/3) |
| ya no quiero las capturas del escritorio, quítalas | llm | undo({}) | esperaba delete_files |
| ya no hace falta que me despiertes mañana | llm | «Perfecto, descansarás bien.» | no ha actuado |
| ¿cómo te llamo sin decir tu nombre? | llm | «Puedes llamarme Nyx.» | no ha actuado |
| ¿guardas lo que te digo? | llm | «Sí, lo guardo. ¿Quieres que te lo repita?» | no ha actuado |
| ¿qué haces cuando estoy jugando? | llm | nyx_control({"setting": "modo partida", "value": "solo voz"}) | esperaba nyx_info |
| mientras juego no pienses, solo obedece órdenes | llm | nyx_control({"setting": "modo partida", "value": "solo voz"}) | setting='modo partida' (esperaba 'cerebro en partida') |
| pásame al inglés el texto que he copiado | llm | «Aún no puedo hacer eso desde aquí. Puedo abrirte la app para que lo hagas tú.» | no ha actuado |
| ábreme una pestaña de incógnito en Chrome | llm | app_action({"action": "new_incognito_window", "app": "Google Chrome"}) | llamada no válida (app_action: Value error, acción desconocida; usa una de: answer_call, back, bookmark, close_tab, command_palette, downloads, find, forward, fullscreen, history, incognito, like, mark_read, new_tab, new_window, next_tab, previous_tab, print, quick_open, quick_switcher, reload, reopen_tab, repeat, save, save_as, search, shuffle, toggle_deafen, toggle_mute, toggle_sidebar, up, volume_down, volume_up, zoom_in, zoom_out, zoom_reset; en Nyx se reintentaría) (1/3) |
| abre el Excel y ponlo a la derecha | llm | open_app({"name": "Excel"}) | plan distinto: ['open_app'] (1/3) |
| silencia el Discord y sube la música | llm | media_control({"action": "pause", "music": false, "source": "discord"}); set_volume({"app": "Spotify", "mute": true}) | plan distinto: ['media_control', 'set_volume'] (1/3) |
| apaga el wifi y bloquea el ordenador | llm | system_power({"action": "shutdown"}); toggle_wifi({"enabled": false}) | plan distinto: ['system_power', 'toggle_wifi'] |
| ¿qué dirección IP tiene mi ordenador? | router | system_info({"what": "ip"}) | esperaba run_powershell |
| ¿cuánto tiempo lleva encendido el PC? | llm | system_info({"what": "top"}) | esperaba run_powershell |
| ¿qué versión de Windows tengo? | llm | «Windows 11 es la versión más reciente que tienes.» | no ha actuado |
