# Batería de frases · 2026-11-17 22:53

Modelo: `nyx-r2:7b`. Frases: 452. **Acierto: 436/452 (96 %)**.

Herramientas: todas (caben en su parte del contexto). Semilla del modelo: 1.

Primer token en lo que pasa por el LLM (primera pasada): mediana **565 ms**, media **636 ms**, peor 1873 ms.

| Camino | Frases | Acierto | Latencia mediana | Peor |
| --- | --- | --- | --- | --- |
| negativa | 7 | 7/7 | 0 ms | 0 ms |
| router | 307 | 307/307 | 0 ms | 10 ms |
| llm | 138 | 122/138 | 701 ms | 3323 ms |

## Fallos

| Frase | Camino | Qué hizo | Por qué |
| --- | --- | --- | --- |
| entra en mi correo de Gmail | llm | «Aún no sé abrirte el correo. Puedo abrirte Gmail o el panel de control. ¿Quieres que te lo abra?» | no ha actuado |
| no encuentro el Excel del presupuesto | llm | open_app({"name": "Excel"}) | esperaba find_files |
| lleva los PDF de Descargas a Documentos | llm | move_files({"destination": "Documentos", "kind": "pdf", "folder": "Descargas"}) | llamada no válida (move_files: Input should be 'images', 'videos', 'documents', 'audio', 'archives', 'installers' or 'folders'; en Nyx se reintentaría) (1/3) |
| pasa las capturas del escritorio a Imágenes | llm | move_files({"destination": "Imágenes"}) | llamada no válida (move_files: Field required; en Nyx se reintentaría) (1/3) |
| ya no quiero las capturas del escritorio, quítalas | llm | undo({}) | esperaba delete_files |
| ya no hace falta que me despiertes mañana | llm | «No hay alarmas para mañana. Si quieres, te las puedo poner.» | no ha actuado |
| ¿cómo te llamo sin decir tu nombre? | llm | «Puedes llamarme Nyx.» | no ha actuado |
| ¿guardas lo que te digo? | llm | «Aún no sé guardar archivos. Si quieres, te abro el Bloc de notas y lo escribes tú.» | no ha actuado |
| ¿qué haces cuando estoy jugando? | llm | nyx_control({"value": "solo voz", "setting": "modo partida"}) | esperaba nyx_info |
| mientras juego no pienses, solo obedece órdenes | llm | nyx_control({"setting": "modo partida", "value": "solo voz"}) | setting='modo partida' (esperaba 'cerebro en partida') |
| pásame al inglés el texto que he copiado | llm | type_text({"app": "Bloc de notas", "text": "Here's the copied text"}) | esperaba clipboard |
| ábreme una pestaña de incógnito en Chrome | llm | app_action({"action": "new_incognito_window", "app": "Google Chrome"}) | llamada no válida (app_action: Value error, acción desconocida; usa una de: answer_call, back, bookmark, close_tab, command_palette, downloads, find, forward, fullscreen, history, incognito, like, mark_read, new_tab, new_window, next_tab, previous_tab, print, quick_open, quick_switcher, reload, reopen_tab, repeat, save, save_as, search, shuffle, toggle_deafen, toggle_mute, toggle_sidebar, up, volume_down, volume_up, zoom_in, zoom_out, zoom_reset; en Nyx se reintentaría) (1/3) |
| abre el Excel y ponlo a la derecha | llm | open_app({"name": "Excel"}) | plan distinto: ['open_app'] (1/3) |
| silencia el Discord y sube la música | llm | set_volume({"app": "discord", "mute": true, "music": true}) | llamada no válida (set_volume: Extra inputs are not permitted; en Nyx se reintentaría) (1/3) |
| ¿cuánto tiempo lleva encendido el PC? | llm | system_info({"what": "top"}) | esperaba run_powershell |
| ¿qué versión de Windows tengo? | llm | «Windows 11 es la versión más reciente que tienes.» | no ha actuado |
