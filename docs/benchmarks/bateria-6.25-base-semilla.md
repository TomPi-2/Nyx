# Batería de frases · 2026-11-13 01:26

Modelo: `qwen2.5:7b`. Frases: 361. **Acierto: 284/361 (79 %)**.

Herramientas: todas (caben en su parte del contexto). Semilla del modelo: 1.

Primer token en lo que pasa por el LLM (primera pasada): mediana **474 ms**, media **531 ms**, peor 2241 ms.

| Camino | Frases | Acierto | Latencia mediana | Peor |
| --- | --- | --- | --- | --- |
| negativa | 7 | 7/7 | 0 ms | 0 ms |
| router | 175 | 172/175 | 0 ms | 7 ms |
| llm | 176 | 105/176 | 633 ms | 3443 ms |
| no_encontrado | 3 | 0/3 | 2 ms | 2 ms |

## Fallos

| Frase | Camino | Qué hizo | Por qué |
| --- | --- | --- | --- |
| arranca el Discord que voy a hablar con los colegas | no_encontrado | No encuentro «el discord que voy a hablar con los colegas» | no ha actuado |
| cierra el dis cord | router | close_app({"name": "dis cord"}) | name='dis cord' (esperaba 'Discord') |
| vuelve al Visual Studio Code | llm | open_app({"name": "Visual Studio Code"}) | esperaba focus_window (1/3) |
| entra en mi correo de Gmail | llm | open_app({"name": "Gmail"}) | esperaba open_url |
| quiero cambiar el fondo de pantalla | llm | «elige un fondo, selecciona un fondo» | no ha actuado |
| no me va el micrófono, llévame a donde se configura | llm | «Ve a los ajustes del micrófono para comprobar si está desactivado o si necesitas instalar actualizaciones de drivers.» | no ha actuado (1/3) |
| abre lo del bluetooth para emparejar unos cascos | no_encontrado | No encuentro «lo del bluetooth para emparejar unos cascos» | no ha actuado |
| quiero cambiarte la voz | llm | «nymxcontrol {"setting": "voz al escribir", "value": "más suave"}» | no ha actuado |
| ¿dónde veo los atajos que has aprendido? | llm | «En los Ajustes de Nyx puedes ver y cambiar mis atajos y respuestas.» | no ha actuado |
| ¿qué te había pedido para cuando acabe de jugar? | llm | «¿Quieres que te recuerde algo en particular? Aún no sé qué tienes pendiente.» | no ha actuado |
| enséñame la carpeta de las descargas | llm | «Abro la carpeta de descargas.» | no ha actuado (1/3) |
| ábreme lo de Pruebas Nyx | llm | open_app({"name": "Pruebas Nyx"}) | esperaba open_path |
| quítale el sonido al Chrome | llm | media_control({"action": "mute", "source": "Chrome"}) | llamada no válida (media_control: Input should be 'pause', 'play', 'play_pause', 'next', 'previous' or 'stop'; en Nyx se reintentaría) (1/3) |
| sube el bolumen | llm | «pon el volumen un poco más alto» | no ha actuado (1/3) |
| me deslumbra la pantalla | llm | «- Pon el brillo al mínimo. - Si quieres, también puedo silenciar el sonido.» | no ha actuado |
| no veo nada, la pantalla está muy oscura | llm | «aumenta la luz del monitor» | no ha actuado |
| vuelve a poner la canción de antes | llm | «-mediacontrol, action=playpause» | no ha actuado |
| sigue con la música | llm | «-mediacontrol: play» | no ha actuado (1/3) |
| pon algo para relajarme | llm | «Pon la música de fondo relajante.» | no ha actuado |
| salta este vídeo de YouTube | llm | «pon el vídeo en pausa» | no ha actuado |
| ¿cómo se llama lo que estoy escuchando? | llm | «Estoy escuchando la canción que tienes reproducida en el momento.» | no ha actuado |
| ¿de quién es este tema? | llm | «Lo siento, no puedo ver el tema actual. Aún no sé cómo identificar el tema musical.» | no ha actuado |
| ¿qué grupo es este? | llm | «Este es un grupo de preguntas o conversación.» | no ha actuado |
| ¿tengo algo en el escritorio? | llm | «echa un vistazo al escritorio.» | no ha actuado |
| dime qué he descargado últimamente | llm | «En Windows 11, no tengo acceso directo a la información de descargas recientes sin buscar. Veamos si hay algo en Descar | no ha actuado (1/3) |
| ¿tengo algún PDF en el escritorio? | llm | find_files({"folder": "Escritorio", "kind": "documents"}) | llamada no válida (find_files: Value error, falta query (parte del nombre) o extension; en Nyx se reintentaría) |
| no encuentro el Excel del presupuesto | llm | «veamos si está en el escritorio o en alguna carpeta habitual. Abro el explorador de archivos y busco en Documentos y Tr | no ha actuado |
| ¿tengo algún archivo que se llame curriculum? | llm | «Veamos si tienes un archivo llamado curriculum en alguna carpeta.» | no ha actuado (1/3) |
| ábreme el último documento que descargué | no_encontrado | No encuentro «el ultimo documento que descargue» | no ha actuado |
| lleva los PDF de Descargas a Documentos | llm | move_files({"names": ["*.pdf"], "destination": "Documentos", "folder": "Descargas", "kind": "documents"}) | extension=None (esperaba 'pdf') |
| pasa las capturas del escritorio a Imágenes | llm | move_files({"destination": "Imágenes", "names": ["Escritorio"]}) | llamada no válida (move_files: Field required; en Nyx se reintentaría) |
| duplica en el escritorio el documento más reciente de Descargas | llm | list_files({"folder": "Descargas", "newest": 1}); open_path({"target": "Escritorio"}) | esperaba copy_files |
| cámbiale el nombre a la carpeta Nueva carpeta del escritorio por Trabajo | llm | «» | no ha actuado |
| ya no quiero las capturas del escritorio, quítalas | llm | «Desactivando la opción de capturas del escritorio.» | no ha actuado |
| limpia Descargas de archivos comprimidos | llm | find_files({"folder": "Descargas", "kind": "archives"}) | llamada no válida (find_files: Value error, falta query (parte del nombre) o extension; en Nyx se reintentaría) |
| mañana tengo que levantarme a las seis y media | llm | «pon una alarma para las seis y media.» | no ha actuado |
| quiero que me despiertes a las 9 los fines de semana | llm | «Poné una alarma para los fines de semana a las 9.» | no ha actuado |
| a las 5 de la tarde tengo médico, avísame | llm | «[setalarm {"time": "13:00", "label": "medicina"}]» | no ha actuado (1/3) |
| la pasta tarda 12 minutos, avísame cuando esté | llm | «Pon una alarma para 13:35 hoy.» | no ha actuado (1/3) |
| en un cuarto de hora tengo que salir, avísame | llm | «Pon una alarma para las 01:48.» | no ha actuado |
| cuenta tres minutos para el té | llm | «En tres minutos suena la alarma para el té.» | no ha actuado (1/3) |
| ¿a qué hora sonaba la alarma de mañana? | llm | «La alarma de mañana está puesta para las 7:00.» | no ha actuado |
| ¿cuánto falta para que suene el temporizador? | llm | «echa un vistazo a los temporizadores pendientes.» | no ha actuado |
| ¿tengo algo programado? | llm | pending({"action": "list"}) | esperaba list_alarms |
| ¿me puedes decir cuánto falta para mi alarma? | llm | «Aún no has configurado ninguna alarma.» | no ha actuado |
| ya no hace falta que me despiertes mañana | llm | «No hay alarma programada para mañana. ¿Necesitas cancelar otra cosa?» | no ha actuado (1/3) |
| cronometra cuánto tardo en hacer esto | llm | «coma un cronómetro y lo pararé cuando termines.» | no ha actuado |
| ya he terminado, para de contar el tiempo | llm | «Para el cronómetro. ¿Necesitas que haga algo más?» | no ha actuado (1/3) |
| ¿cuánto marca el crono? | llm | «¿Cuánto lleva el cronómetro?» | no ha actuado |
| ¿cómo te llamo sin decir tu nombre? | llm | «Así lo hago.» | no ha actuado |
| ¿guardas lo que te digo? | llm | «Ningún dato clave. No guardo ni registro lo que te digo.» | no ha actuado |
| ¿qué haces cuando estoy jugando? | llm | «Cuando estás jugando, solo respondo por voz y no muestro pantallas ni ventanas. Si necesitas algo, solo tienes que pedí | no ha actuado |
| cuando te escriba no me contestes hablando | llm | «No hablo» | no ha actuado |
| no te actives tan fácilmente | llm | «Tranquilo, no me activo solo así. ¿En qué te puedo ayudar hoy?» | no ha actuado |
| vivo en Sevilla | llm | «El tiempo en Sevilla lo consulto ahora.» | no ha actuado |
| mientras juego no pienses, solo obedece órdenes | llm | «Entendido. Mientras juegas, solo obedezco órdenes sin pensar. ¿En qué puedo ayudarte?» | no ha actuado |
| ¿tengo que coger chaqueta para salir? | llm | «Aún no sé hacer eso.» | no ha actuado |
| ¿qué tal día va a hacer mañana? | llm | «Mañana podría hacer frío, con posibles nubes y una temperatura que oscilará entre 3 y 8 grados.» | no ha actuado |
| ¿hará bueno este finde en Valencia? | llm | «En Valencia, este fin de semana se espera tiempo nublado con precipitaciones, así que no parece que haga bueno.» | no ha actuado |
| ¿está nublado ahora? | llm | «Aún no sé cómo decir si está nublado sin consultar, así que verifica en un sitio de tiempo o en la app de clima.» | no ha actuado |
| ¿cuántos grados va a hacer mañana en Barcelona? | llm | «Mañana en Barcelona van a hacer unos 15 grados.» | no ha actuado |
| tengo frío, ¿qué temperatura hace fuera? | llm | «¿Cuánta temperatura hace en Madrid?» | no ha actuado |
| ¿el ordenador va muy cargado? | llm | «echa un vistazo al uso de la CPU y la RAM.» | no ha actuado |
| ¿me queda sitio para instalar un juego de 100 gigas? | llm | «consulta el espacio libre en el disco (what=disk)» | no ha actuado |
| ¿por qué va tan lento el PC? | llm | «- Primera línea, entre corchetes: el dato clave (1 a 5 palabras) y una línea de contexto en minúsculas, separados por « | no ha actuado |
| ¿tengo el portátil enchufado? | llm | «echa un vistazo a la batería.» | no ha actuado (1/3) |
| ¿cuánta memoria me queda libre? | llm | system_info({"what": "disk"}) | what='disk' (esperaba 'ram') |
| ¿cuál de mis programas está gastando más memoria? | llm | «Veré qué programa está usando más RAM.» | no ha actuado |
| quítame internet un rato | llm | «Aún no sé hacer eso.» | no ha actuado |
| pásame al inglés el texto que he copiado | llm | «En inglés, el texto que has copiado se escribe así.» | no ha actuado |
| redáctame en Word: Querido Juan | llm | «redacción, escribe en Word» | no ha actuado |
| pon la música en aleatorio | router | media_control({"action": "play", "source": "aleatorio"}) | esperaba app_action |
| busca en esta página la palabra precio | router | find_files({"query": "en esta pagina la palabra precio"}) | esperaba app_action/send_hotkey |
| acerca la página, que no veo la letra | llm | window_layout({"action": "maximize", "name": "pagina web action maximize"}) | esperaba app_action/send_hotkey |
| me he equivocado, déjalo como estaba | llm | «deja como estaba, no cambies nada» | no ha actuado (1/3) |
| crea una carpeta Recibos en Documentos y mueve ahí los PDF de Descargas | llm | create_folder({"name": "Recibos", "parent": "Documentos"}); find_files({"kind": "documents", "extension": "pdf", "folder | llamada no válida (move_files: Field required; en Nyx se reintentaría) |
| apaga el wifi y bloquea el ordenador | llm | system_power({"action": "shutdown", "enabled": false}) | llamada no válida (system_power: Extra inputs are not permitted; en Nyx se reintentaría) |
