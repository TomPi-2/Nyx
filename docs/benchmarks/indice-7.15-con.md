# Batería de frases · 2026-11-14 03:16

Modelo: `nyx-r2:7b`. Frases: 409. **Acierto: 387/409 (95 %)**.

Herramientas: fijas + grupos usados hace poco (no caben con 8192 de contexto). Semilla del modelo: 1.

Primer token en lo que pasa por el LLM (primera pasada): mediana **455 ms**, media **528 ms**, peor 1884 ms.

| Camino | Frases | Acierto | Latencia mediana | Peor |
| --- | --- | --- | --- | --- |
| negativa | 7 | 7/7 | 0 ms | 0 ms |
| router | 268 | 268/268 | 0 ms | 5 ms |
| llm | 134 | 112/134 | 505 ms | 1884 ms |

## Fallos

| Frase | Camino | Qué hizo | Por qué |
| --- | --- | --- | --- |
| quiero escuchar música en Spotify | llm | open_app({"name": "Spotify"}); media_control({"music": true}) | llamada no válida (media_control: Field required; en Nyx se reintentaría) |
| enséñame el Spotify que lo tengo abierto | llm | app_action({"action": "play"}) | llamada no válida (app_action: Value error, acción desconocida; usa una de: answer_call, back, bookmark, close_tab, command_palette, downloads, find, forward, fullscreen, history, incognito, like, mark_read, new_tab, new_window, next_tab, previous_tab, print, quick_open, quick_switcher, reload, reopen_tab, repeat, save, save_as, search, shuffle, toggle_deafen, toggle_mute, toggle_sidebar, up, volume_down, volume_up, zoom_in, zoom_out, zoom_reset; en Nyx se reintentaría) |
| entra en mi correo de Gmail | llm | «Aún no sé hacer eso. Puedo abrirte la web o abrirte Gmail si lo tienes.» | no ha actuado |
| está muy alto el sonido | llm | «Lo bajo.» | no ha actuado |
| no encuentro el Excel del presupuesto | llm | «Puedo abrirte Excel. ¿Quieres que lo haga?» | no ha actuado |
| limpia Descargas de archivos comprimidos | llm | delete_files({"extension": "rar", "folder": "Descargas"}) | kind=None (esperaba 'archives') (1/3) |
| ya no hace falta que me despiertes mañana | llm | «No hay alarma para mañana. Puedo poner una si quieres.» | no ha actuado (1/3) |
| ¿cómo te llamo sin decir tu nombre? | llm | «Puedes pedirme cosas sin nombrarme.» | no ha actuado |
| ¿guardas lo que te digo? | llm | «No guardo nada.» | no ha actuado |
| ¿qué haces cuando estoy jugando? | llm | nyx_control({"setting": "modo partida", "value": "solo voz"}) | esperaba nyx_info |
| mientras juego no pienses, solo obedece órdenes | llm | nyx_control({"setting": "modo partida", "value": "solo voz"}) | setting='modo partida' (esperaba 'cerebro en partida') |
| pásame al inglés el texto que he copiado | llm | «Pégalo y te lo paso al inglés.» | no ha actuado (1/3) |
| redáctame en Word: Querido Juan | llm | «Abro Microsoft Word. ¿Quieres que te abra una nueva página o te escriba directamente?» | no ha actuado |
| ábreme una pestaña de incógnito en Chrome | llm | app_action({"app": "Chrome", "action": "new_tab"}) | action='new_tab' (esperaba 'incognito') |
| abre el Excel y ponlo a la derecha | llm | open_app({"name": "excel"}) | plan distinto: ['open_app'] |
| silencia el Discord y sube la música | llm | media_control({"action": "pause", "source": "discord"}); set_volume({"app": "spotify", "change": 50}) | plan distinto: ['media_control', 'set_volume'] |
| haz una captura y abre la carpeta de capturas | llm | screenshot({"target": "current"}) | plan distinto: ['screenshot'] (1/3) |
| apaga el wifi y bloquea el ordenador | llm | system_power({"action": "lock"}) | plan distinto: ['system_power'] |
| ¿hará calor el sábado? | llm | «Un rango típico para la temperatura en muchas partes suele ser entre 20 y 25 grados. Sin embargo, esto puede variar seg | no ha actuado |
| pasado mañana tengo que levantarme a las 8 | llm | «Pon la alarma para pasado mañana a las 8.» | no ha actuado |
| ¿qué versión de Windows tengo? | llm | «Aún no sé mostrar la versión. Puedo abrirte la configuración para que la busques tú.» | no ha actuado |
| búscame un tutorial para hacer tablas dinámicas en Excel | llm | open_url({"target": "tutorial dinámicas en excel"}) | esperaba web_search |
