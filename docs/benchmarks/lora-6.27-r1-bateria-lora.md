# Batería de frases · 2026-11-13 10:38

Modelo: `lora`. Frases: 400. **Acierto: 373/400 (93 %)**.

Herramientas: todas (caben en su parte del contexto). Semilla del modelo: 1.

Primer token en lo que pasa por el LLM (primera pasada): mediana **7737 ms**, media **8114 ms**, peor 13158 ms.

| Camino | Frases | Acierto | Latencia mediana | Peor |
| --- | --- | --- | --- | --- |
| negativa | 7 | 7/7 | 0 ms | 0 ms |
| router | 263 | 263/263 | 0 ms | 5 ms |
| llm | 130 | 103/130 | 7736 ms | 13158 ms |

## Fallos

| Frase | Camino | Qué hizo | Por qué |
| --- | --- | --- | --- |
| copia las fotos de Descargas a Imágenes | llm | copy_files({"folder": "descargas", "destination": "imagenes"}) | kind=None (esperaba 'images') (1/3) |
| abre el bloc de notas y abre una pestaña nueva | llm | open_app({"name": "Bloc de notas"}); wait_for_window({"name": "Bloc de notas"}); app_action({"action": "new"}) | llamada no válida (app_action: Value error, acción desconocida; usa una de: answer_call, back, bookmark, close_tab, command_palette, downloads, find, forward, fullscreen, history, incognito, like, mark_read, new_tab, new_window, next_tab, previous_tab, print, quick_open, quick_switcher, reload, reopen_tab, repeat, save, save_as, search, shuffle, toggle_deafen, toggle_mute, toggle_sidebar, up, volume_down, volume_up, zoom_in, zoom_out, zoom_reset; en Nyx se reintentaría) |
| cuenta del 1 al 10 | llm | media_control({"action": "play", "music": true}) | ha actuado |
| manda un whatsapp a mi madre | llm | send_whatsapp({"message": "Hola mamá, ¿cómo estás?"}) | ha actuado |
| Crea tres archivos de texto | llm | create_folder({"name": "archivos de texto"}) | ha actuado |
| quiero el Discord en la mitad izquierda de la pantalla | llm | window_layout({"action": "left_half", "name": "discord"}) | llamada no válida (window_layout: Input should be 'maximize', 'minimize', 'restore', 'left', 'right' or 'next_monitor'; en Nyx se reintentaría) |
| entra en mi correo de Gmail | llm | open_app({"name": "Gmail"}) | esperaba open_url |
| no encuentro el Excel del presupuesto | llm | open_app({"name": "Excel"}) | esperaba find_files (1/3) |
| pasa las capturas del escritorio a Imágenes | llm | move_files({"folder": "Imágenes", "names": ["Capturas"]}) | llamada no válida (move_files: Field required; en Nyx se reintentaría) |
| ya no quiero las capturas del escritorio, quítalas | llm | undo({}) | esperaba delete_files |
| ¿cómo te llamo sin decir tu nombre? | llm | focus_window({"name": "ventana del usuario"}) | esperaba nyx_info |
| ¿guardas lo que te digo? | llm | pending({"action": "list"}) | esperaba nyx_info |
| ¿qué haces cuando estoy jugando? | llm | nyx_control({"setting": "modo partida", "value": "solo voz"}) | esperaba nyx_info |
| mientras juego no pienses, solo obedece órdenes | llm | undo({}) | esperaba nyx_control |
| pásame al inglés el texto que he copiado | llm | type_text({"text": "Now is November 13, 2026, 10:20."}) | esperaba clipboard |
| redáctame en Word: Querido Juan | llm | open_app({"name": "Word"}) | esperaba type_text |
| ábreme una pestaña de incógnito en Chrome | llm | open_app({"name": "Google Chrome", "incognito": true}) | llamada no válida (open_app: Extra inputs are not permitted; en Nyx se reintentaría) (1/3) |
| apaga el wifi y bloquea el ordenador | llm | system_power({"action": "lock"}); toggle_wifi({"enabled": false}) | plan distinto: ['system_power', 'toggle_wifi'] |
| hola, ¿qué tal estás? | llm | nyx_info({"topic": "modo partida"}) | ha actuado (1/3) |
| ¿qué hora será ahora en Nueva York? | llm | set_timer({"minutes": 1}) | ha actuado |
| manda un correo a mi jefe diciendo que llego tarde | llm | type_text({"text": "Estimado/a jefe, lamento llegar tarde hoy. Estoy trabajando en resolver un problema que se presentó  | ha actuado |
| pídeme una pizza | llm | set_timer({"minutes": 15, "label": "pedir pizza"}) | ha actuado |
| publica en Instagram la última foto | llm | open_app({"name": "Instagram"}) | ha actuado |
| llama a mi hermano | llm | open_url({"target": "whatsapp://call/123456789"}) | ha actuado |
| pasado mañana tengo que levantarme a las 8 | llm | set_alarm({"time": "08:00", "day": "pasado mañana"}) | llamada no válida (set_alarm: Input should be 'today' or 'tomorrow'; en Nyx se reintentaría) |
| ¿cuánto tiempo lleva encendido el PC? | llm | system_info({"what": "top"}) | esperaba run_powershell |
| ¿qué versión de Windows tengo? | llm | system_info({"what": "version"}) | llamada no válida (system_info: Input should be 'battery', 'cpu', 'ram', 'disk' or 'top'; en Nyx se reintentaría) |
