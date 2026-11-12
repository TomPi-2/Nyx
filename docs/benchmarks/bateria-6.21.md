# Batería de frases · 2026-11-12 21:36

Modelo: `qwen2.5:7b`. Frases: 337. **Acierto: 262/337 (78 %)**.

Herramientas: todas (caben en su parte del contexto).

Primer token en lo que pasa por el LLM (primera pasada): mediana **355 ms**, media **381 ms**, peor 1327 ms.

| Camino | Frases | Acierto | Latencia mediana | Peor |
| --- | --- | --- | --- | --- |
| negativa | 7 | 7/7 | 0 ms | 0 ms |
| router | 142 | 139/142 | 0 ms | 37 ms |
| llm | 185 | 116/185 | 406 ms | 1783 ms |
| no_encontrado | 3 | 0/3 | 1 ms | 2 ms |

## Fallos

| Frase | Camino | Qué hizo | Por qué |
| --- | --- | --- | --- |
| necesito la calculadora | llm | «Aún no sé hacer eso.» | no ha actuado |
| arranca el Discord que voy a hablar con los colegas | no_encontrado | No encuentro «el discord que voy a hablar con los colegas» | no ha actuado |
| vamos a echar una partida al Fortnite | llm | open_settings({"page": "partida"}) | esperaba open_app |
| tengo que hacer una hoja de cálculo | llm | «Aún no sé hacer eso.» | no ha actuado |
| quiero grabar la pantalla con el OBS | llm | «Aún no sé cómo hacer eso.» | no ha actuado |
| cierra el dis cord | router | close_app({"name": "dis cord"}) | name='dis cord' (esperaba 'Discord') |
| pon el Chrome en grande | llm | open_app({"name": "Chrome", "focus": true}) | esperaba window_layout |
| quita de en medio esta ventana | llm | close_app({"name": null}) | esperaba window_layout |
| minimisa el crome | llm | focus_window({"name": "Chrome", "action": "minimize"}) | llamada no válida (focus_window: Extra inputs are not permitted; en Nyx se reintentaría) |
| entra en mi correo de Gmail | llm | open_app({"name": "Gmail"}) | esperaba open_url |
| quiero cambiar el fondo de pantalla | llm | «configura el fondo de pantalla, ajustes de pantalla» | no ha actuado |
| no me va el micrófono, llévame a donde se configura | llm | «Ve a los ajustes de sonido para ver si el micrófono está habilitado y correctamente conectado.» | no ha actuado |
| abre lo del bluetooth para emparejar unos cascos | no_encontrado | No encuentro «lo del bluetooth para emparejar unos cascos» | no ha actuado |
| quiero cambiarte la voz | llm | «nychcontrol {"setting": "voz al escribir", "value": "más natural"}» | no ha actuado |
| ¿dónde veo los atajos que has aprendido? | llm | «Puedes ver los atajos que he aprendido en los ajustes de partida.» | no ha actuado |
| ¿qué te había pedido para cuando acabe de jugar? | llm | «/ ¿Quieres que haga algo especial cuando acabe de jugar? Ya te lo pregunté antes.» | no ha actuado |
| enséñame la carpeta de las descargas | llm | «Abro la carpeta de descargas.» | no ha actuado (1/3) |
| ábreme lo de Pruebas Nyx | llm | open_app({"name": "Pruebas Nyx"}) | esperaba open_path |
| no veo nada, la pantalla está muy oscura | llm | «Voy a subir un poco el brillo de la pantalla.» | no ha actuado (1/3) |
| vuelve a poner la canción de antes | llm | «reproduce la última canción que estabas escuchando» | no ha actuado |
| pon algo para relajarme | llm | «relaja música suave» | no ha actuado |
| salta este vídeo de YouTube | llm | media_control({"action": "pause", "source": "youtube"}) | action='pause' (esperaba 'next') |
| ¿cómo se llama lo que estoy escuchando? | llm | «lo que estás escuchando.» | no ha actuado |
| ¿de quién es este tema? | llm | «Lo siento, no puedo ver el tema actual. ¿Podrías decirme de quién es si lo recuerdas?» | no ha actuado |
| ¿qué grupo es este? | llm | «No reconozco este grupo. ¿Podrías darme más información?» | no ha actuado |
| ¿tengo algo en el escritorio? | llm | «Veamos si hay algo en el escritorio.» | no ha actuado |
| dime qué he descargado últimamente | llm | «Veamos qué has descargado últimamente.» | no ha actuado |
| ¿tengo algún PDF en el escritorio? | llm | «Voy a buscar un PDF en tu escritorio. ¿Hay algún nombre en particular que recuerdes?» | no ha actuado |
| no encuentro el Excel del presupuesto | llm | «busca Excel, busco el archivo de Excel» | no ha actuado |
| ábreme el último documento que descargué | no_encontrado | No encuentro «el ultimo documento que descargue» | no ha actuado |
| lleva los PDF de Descargas a Documentos | llm | move_files({"folder": "Descargas", "kind": "documents", "names": ["*.pdf"]}) | llamada no válida (move_files: Field required; en Nyx se reintentaría) |
| pasa las capturas del escritorio a Imágenes | llm | move_files({"destination": "Imágenes", "names": ["Escritorio"]}) | llamada no válida (move_files: Field required; en Nyx se reintentaría) |
| duplica en el escritorio el documento más reciente de Descargas | llm | open_path({"target": "Descargas"}); list_files({"folder": "Descargas", "newest": 1}); open_path({"target": "Escritorio"} | esperaba copy_files (1/3) |
| cámbiale el nombre a la carpeta Nueva carpeta del escritorio por Trabajo | llm | «» | no ha actuado |
| ya no quiero las capturas del escritorio, quítalas | llm | open_settings({"page": "capturas"}) | esperaba delete_files |
| limpia Descargas de archivos comprimidos | llm | find_files({"folder": "Descargas", "kind": "archives"}); delete_files({"folder": "Descargas", "kind": "archives"}) | llamada no válida (find_files: Value error, falta query (parte del nombre) o extension; en Nyx se reintentaría) |
| mañana tengo que levantarme a las seis y media | llm | «Poné una alarma para las seis y media de la mañana para que no te pille dormido.» | no ha actuado |
| quiero que me despiertes a las 9 los fines de semana | llm | «Pon una alarma para los fines de semana a las 9.» | no ha actuado |
| a las 5 de la tarde tengo médico, avísame | llm | «pon una alarma para las 15:00.» | no ha actuado |
| la pasta tarda 12 minutos, avísame cuando esté | llm | «Pon una alarma para 21:46.» | no ha actuado |
| en un cuarto de hora tengo que salir, avísame | llm | «Pon una alarma para las 21:45, que tienes que salir en un cuarto de hora.» | no ha actuado |
| ¿a qué hora sonaba la alarma de mañana? | llm | «Para saber a qué hora sonaba la alarma de mañana, necesitaría que me dijeras su nombre o descripción. Si no recuerdas e | no ha actuado |
| ¿cuánto falta para que suene el temporizador? | llm | «Si no tienes ningún temporizador programado, no hay ninguno sufriendo.» | no ha actuado |
| ¿tengo algo programado? | llm | «echa un vistazo a tus alarmas y recordatorios.» | no ha actuado |
| ¿me puedes decir cuánto falta para mi alarma? | llm | «Para saber cuánto falta para tu alarma, necesito que me indiques la hora exacta a la que está puesta. ¿Puedes decírmela | no ha actuado |
| ya no hace falta que me despiertes mañana | llm | set_alarm({"time": "07:00", "repeat": "none", "label": "Despertar", "day": "today"}) | esperaba cancel_alarm |
| ¿cuánto marca el crono? | llm | «El cronómetro marca 1 hora y 23 minutos.» | no ha actuado |
| ¿cómo te llamo sin decir tu nombre? | llm | «simplemente / sin nombre específico Sin nombre específico.» | no ha actuado |
| ¿guardas lo que te digo? | llm | «grabas, grabo las voces» | no ha actuado |
| ¿qué haces cuando estoy jugando? | llm | «Cuando estás jugando, Nyx solo responde por voz y no muestra nada en pantalla. El cerebro de Nyx también reduce la acti | no ha actuado |
| cuando te escriba no me contestes hablando | llm | «no hablo, no contesto hablando» | no ha actuado |
| no te actives tan fácilmente | llm | «Entendido, estaré más atento a tus instrucciones. ¿En qué puedo ayudarte hoy?» | no ha actuado |
| vivo en Sevilla | llm | «Estoy en Sevilla. ¿En qué puedo ayudarte hoy?» | no ha actuado |
| mientras juego no pienses, solo obedece órdenes | llm | «Entendido. Mientras juegues, solo obedezco órdenes sin pensar. ¿En qué puedo ayudarte?» | no ha actuado |
| ¿tengo que coger chaqueta para salir? | llm | «[si no llovera / no necesitas chaqueta · si llovera / lleva chaqueta]» | no ha actuado |
| ¿qué tal día va a hacer mañana? | llm | «Mañana no va a llover, pero la temperatura será de 10°C.» | no ha actuado |
| ¿hará bueno este finde en Valencia? | llm | «En Valencia, este fin de semana se espera tiempo nublado con precipitaciones, así que no parece que haga bueno.» | no ha actuado |
| ¿está nublado ahora? | llm | «Aún no sé cómo decir si está nublado sin consultar, pero según la fecha, hoy es jueves 12 de noviembre de 2026. Para sa | no ha actuado |
| ¿cuántos grados va a hacer mañana en Barcelona? | llm | «Mañana en Barcelona hará 15 grados.» | no ha actuado |
| tengo frío, ¿qué temperatura hace fuera? | llm | «¿Qué temperatura hace en Madrid?» | no ha actuado |
| ¿el ordenador va muy cargado? | llm | «echa un vistazo al uso de la CPU y la RAM.» | no ha actuado |
| ¿me queda sitio para instalar un juego de 100 gigas? | llm | «consulta el espacio libre en el disco (what=disk)» | no ha actuado |
| ¿por qué va tan lento el PC? | llm | «Primero, veamos el estado del PC para ver qué está consumiendo más recursos.» | no ha actuado |
| ¿tengo el portátil enchufado? | llm | «Systeminfo {"what": "battery"}» | no ha actuado |
| ¿cuánta memoria me queda libre? | llm | «Aún no sé cuánta memoria libre tienes.» | no ha actuado |
| ¿cuál de mis programas está gastando más memoria? | llm | system_info({"what": "ram"}) | what='ram' (esperaba 'top') |
| quítame internet un rato | llm | «Aún no sé hacer eso.» | no ha actuado |
| pásame al inglés el texto que he copiado | llm | «En inglés, el texto que has copiado es: the text you copied.» | no ha actuado |
| redáctame en Word: Querido Juan | llm | «Abro el Bloc de notas y escribo: «Querido Juan». Ahora, ¿deseas que lo transfiera a Word o lo guardo así?» | no ha actuado |
| ábreme una pestaña de incógnito en Chrome | llm | app_action({"action": "new_incognito_window", "app": "Chrome"}) | llamada no válida (app_action: Value error, acción desconocida; usa una de: answer_call, back, bookmark, close_tab, command_palette, downloads, find, forward, fullscreen, history, incognito, like, mark_read, new_tab, new_window, next_tab, previous_tab, print, quick_open, quick_switcher, reload, reopen_tab, repeat, save, save_as, search, shuffle, toggle_deafen, toggle_mute, toggle_sidebar, up, volume_down, volume_up, zoom_in, zoom_out, zoom_reset; en Nyx se reintentaría) |
| pon la música en aleatorio | router | media_control({"action": "play", "source": "aleatorio"}) | esperaba app_action |
| busca en esta página la palabra precio | router | find_files({"query": "en esta pagina la palabra precio"}) | esperaba app_action/send_hotkey |
| acerca la página, que no veo la letra | llm | «-maximiza la página (si no está maximizada) o desplázate hacia abajo (si ya está al máximo).» | no ha actuado (1/3) |
| crea una carpeta Recibos en Documentos y mueve ahí los PDF de Descargas | llm | create_folder({"name": "Recibos", "parent": "Documentos"}); move_files({"destination": "Documentos/Recibos", "folder": " | llamada no válida (move_files: Input should be 'images', 'videos', 'documents', 'audio', 'archives', 'installers' or 'folders'; en Nyx se reintentaría) |
| apaga el wifi y bloquea el ordenador | llm | system_power({"action": "shutdown", "enabled": false}) | llamada no válida (system_power: Extra inputs are not permitted; en Nyx se reintentaría) |
