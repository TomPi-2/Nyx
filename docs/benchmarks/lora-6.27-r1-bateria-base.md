# Batería de frases · 2026-11-13 11:15

Modelo: `base`. Frases: 400. **Acierto: 341/400 (85 %)**.

Herramientas: todas (caben en su parte del contexto). Semilla del modelo: 1.

Primer token en lo que pasa por el LLM (primera pasada): mediana **5410 ms**, media **5677 ms**, peor 15008 ms.

| Camino | Frases | Acierto | Latencia mediana | Peor |
| --- | --- | --- | --- | --- |
| negativa | 7 | 7/7 | 0 ms | 0 ms |
| router | 263 | 263/263 | 0 ms | 5 ms |
| llm | 130 | 71/130 | 5484 ms | 11518 ms |

## Fallos

| Frase | Camino | Qué hizo | Por qué |
| --- | --- | --- | --- |
| manda esta ventana al otro monitor | llm | «tronchewindow({"action": "nextmonitor"})» | no ha actuado (1/3) |
| vuelve atrás en el navegador | llm | «vuelve la página del navegador» | no ha actuado (1/3) |
| copia las fotos de Descargas a Imágenes | llm | «openpath{"target": "Descargas"} movefiles{"folder": "Descargas", "names": [".jpg", ".png", ".jpeg"], "destination": "Im | no ha actuado |
| abre el bloc de notas y abre una pestaña nueva | llm | open_app({"name": "Bloc de notas"}); wait_for_window({"name": "Bloc de notas"}); app_action({"action": "newueva pestaña" | llamada no válida (app_action: Value error, acción desconocida; usa una de: answer_call, back, bookmark, close_tab, command_palette, downloads, find, forward, fullscreen, history, incognito, like, mark_read, new_tab, new_window, next_tab, previous_tab, print, quick_open, quick_switcher, reload, reopen_tab, repeat, save, save_as, search, shuffle, toggle_deafen, toggle_mute, toggle_sidebar, up, volume_down, volume_up, zoom_in, zoom_out, zoom_reset; en Nyx se reintentaría) |
| bájate la calidad del cristal al mínimo | llm | «nychcontrol{"setting": "calidad del cristal", "value": "mínimo"}» | no ha actuado |
| habla más despacio | llm | «nychcontrol{"setting": "velocidad de la voz", "value": "más despacio"}» | no ha actuado |
| cuando juegue, háblame solo por voz | llm | «nychcontrol{"setting": "modo partida", "value": "solo voz"}» | no ha actuado |
| hazte un poco más grande | llm | «nychcontrol{"setting":"tamaño", "value":"más grande"}» | no ha actuado |
| ya no necesito el Discord, ciérralo | llm | «closeapp(name=Discord)» | no ha actuado |
| enséñame el Spotify que lo tengo abierto | llm | «Escucha en Spotify. ¿Qué quieres hacer?» | no ha actuado |
| manda el Spotify a la otra pantalla | llm | «tronchewindow{"action": "nextmonitor", "name": "Spotify"}» | no ha actuado |
| llévame a las actualizaciones de Windows | llm | «opensettings{"page": "actualizaciones"}» | no ha actuado |
| ¿qué te había pedido para cuando acabe de jugar? | llm | «Te pediste poner una alarma para las 11:00 cuando acabe de jugar.» | no ha actuado |
| olvida lo que te dije para después de la partida | llm | undo({}) | esperaba pending |
| enséñame la carpeta de las descargas | llm | open_path({"target": "C:\\Users\\usuario\\Downloads"}) | target='C:\\Users\\usuario\\Downloads' (esperaba 'Descargas') |
| llévame a mis documentos | llm | open_path({"target": "C:\\Users\\usuario\\Documents"}) | target='C:\\Users\\usuario\\Documents' (esperaba 'Documentos') |
| abre la carpeta donde guardo los proyectos de la uni | llm | «UniProyectos / carpeta similar a donde guardas los proyectos de la universidad Abro la carpeta UniProyectos.» | no ha actuado |
| quita la música un momento | llm | «mediacontrol(action=stop, source=null)» | no ha actuado (1/3) |
| guárdame lo que se ve ahora mismo en la pantalla | llm | «Por ahora no puedo guardar pantallas ni capturar contenido visual. Si quieres leer lo que hay en la pantalla, puedes de | no ha actuado (1/3) |
| ¿qué fotos hay en Imágenes? | llm | «Las fotos de Imágenes son las últimas que has guardado allí.» | no ha actuado |
| ¿cuántos vídeos tengo en la carpeta de vídeos? | llm | «Para saber cuántos vídeos tienes, necesito verificar la carpeta de vídeos. ¿Estás seguro de la ruta? Por defecto, suele | no ha actuado |
| ¿tengo algún PDF en el escritorio? | llm | «¿Tienes algún PDF en el escritorio?» | no ha actuado |
| no encuentro el Excel del presupuesto | llm | «busca el archivo de Excel del presupuesto en tu PC. ¿Sabes dónde suele guardarlo?» | no ha actuado |
| ¿tengo algún archivo que se llame curriculum? | llm | «No tengo información sobre archivos en tu PC, pero puedo buscarlo. ¿Quieres que busque un archivo llamado "curriculum"  | no ha actuado |
| ábreme el último documento que descargué | llm | «abre Descargas si es el último documento, hazlo» | no ha actuado |
| lleva los PDF de Descargas a Documentos | llm | move_files({"folder": "Descargas", "names": ["*.pdf"], "destination": "Documentos"}) | extension=None (esperaba 'pdf') |
| pasa las capturas del escritorio a Imágenes | llm | «movefiles{"folder":"Escritorio", "names": ["Captura1.png", "Captura2.png"], "destination": "Imágenes"}» | no ha actuado (1/3) |
| quita los instaladores de Descargas y ponlos en la carpeta Instaladores | llm | move_files({"folder": "Descargas", "names": ["*.msi", "*.exe"], "destination": "Instaladores"}) | kind=None (esperaba 'installers') |
| haz una copia de las fotos de Descargas en Imágenes | llm | «openpath{"target": "Descargas"} movefiles{"folder": "Descargas", "names": [".jpg", ".png", ".jpeg"], "destination": "Im | no ha actuado |
| duplica en el escritorio el documento más reciente de Descargas | llm | move_files({"folder": "Descargas", "names": ["el más reciente"], "newest": 1, "destination": "Escritorio"}) | esperaba copy_files (1/3) |
| el archivo notas.txt del escritorio llámalo apuntes.txt | llm | «renombrar archivo en Escritorio (folder=Escritorio, name=notas.txt, newname=apuntes.txt)» | no ha actuado |
| ya no quiero las capturas del escritorio, quítalas | llm | undo({}) | esperaba delete_files |
| limpia Descargas de archivos comprimidos | llm | «[elimino archivos comprimidos de Descargas]» | no ha actuado |
| a las 5 de la tarde tengo médico, avísame | llm | «¡Te aviso a las 16:00!» | no ha actuado |
| dentro de 45 minutos recuérdame que mire la lavadora | llm | «{"action": "settimer", "hours": 0, "minutes": 45, "seconds": 0, "label": "mirar la lavadora"}» | no ha actuado |
| ya no hace falta que me despiertes mañana | llm | «no hace falta despertar, ya es tarde» | no ha actuado |
| ¿cómo te llamo sin decir tu nombre? | llm | «llámame Nyx» | no ha actuado |
| ¿guardas lo que te digo? | llm | «No guardo ni registro lo que me dices.» | no ha actuado |
| ¿qué haces cuando estoy jugando? | llm | «funcionario de partida» | no ha actuado |
| habla un poco más rápido | llm | «velocidad de la voz / más rápida» | no ha actuado (1/3) |
| te oigo demasiado lenta, acelera | llm | «nychcontrol {"setting": "velocidad de la voz", "value": "más rápido"}» | no ha actuado |
| hazte más pequeña | llm | «nychcontrol{"setting":"tamaño", "value":"más pequeña"}» | no ha actuado |
| mientras juego no pienses, solo obedece órdenes | llm | «Entendido. Mientras juegas no pensaré ni daré consejos, solo ejecutaré órdenes. ¿Cómo puedo ayudarte ahora?» | no ha actuado |
| vuelve a encender el wifi | llm | «Pon el wifi de nuevo.» | no ha actuado |
| léeme lo que copié antes | llm | «¿Qué has copiado antes?» | no ha actuado |
| pásame al inglés el texto que he copiado | llm | «El texto que has copiado es: "Now is November 13, 2026, 11:03."» | no ha actuado |
| ¿qué pone en lo que tengo copiado? | llm | «讀取粘貼板的内容。» | no ha actuado |
| pon en el bloc de notas: comprar leche | llm | «openpath{"target": "Bloc de notas"} typetext{"text": "comprar leche", "app": null}» | no ha actuado |
| redáctame en Word: Querido Juan | llm | «Escribiré el mensaje en Word. ¿Deseas que incluya algo específico en el correo?» | no ha actuado |
| abre el Excel y ponlo a la derecha | llm | open_app({"name": "Excel"}) | plan distinto: ['open_app'] (1/3) |
| silencia el Discord y sube la música | llm | «silencia Discord y pone el volumen al 50» | no ha actuado |
| crea una carpeta Recibos en Documentos y mueve ahí los PDF de Descargas | llm | create_folder({"name": "Recibos", "parent": "Documentos"}); find_files({"query": "*.pdf", "folder": "Descargas", "kind": | plan distinto: ['create_folder', 'find_files', 'move_files'] |
| apaga el wifi y bloquea el ordenador | llm | system_power({"action": "lock"}); toggle_wifi({"enabled": false}) | plan distinto: ['system_power', 'toggle_wifi'] |
| ¿queda algo de batería? | llm | «consulta la batería.» | no ha actuado |
| ¿hará calor el sábado? | llm | «¿qué temperatura hace en Madrid, temperatura hoy» | no ha actuado |
| pasado mañana tengo que levantarme a las 8 | llm | «pon la alarma para las 8.» | no ha actuado |
| ¿cuánto tiempo lleva encendido el PC? | llm | system_info({"what": "top"}) | esperaba run_powershell |
| ¿qué versión de Windows tengo? | llm | «consulta tu sistema operativo para saber qué versión tienes.» | no ha actuado |
| marca la casilla de recordar contraseña | llm | «Marco la casilla de recordar contraseña.» | no ha actuado (1/3) |
