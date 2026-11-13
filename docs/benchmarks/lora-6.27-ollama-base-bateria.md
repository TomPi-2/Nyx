# Batería de frases · 2026-11-13 16:15

Modelo: `qwen2.5:7b`. Frases: 409. **Acierto: 377/409 (92 %)**.

Herramientas: todas (caben en su parte del contexto). Semilla del modelo: 1.

Primer token en lo que pasa por el LLM (primera pasada): mediana **861 ms**, media **1057 ms**, peor 5185 ms.

| Camino | Frases | Acierto | Latencia mediana | Peor |
| --- | --- | --- | --- | --- |
| negativa | 7 | 7/7 | 0 ms | 0 ms |
| router | 267 | 267/267 | 0 ms | 15 ms |
| llm | 135 | 103/135 | 1310 ms | 5185 ms |

## Fallos

| Frase | Camino | Qué hizo | Por qué |
| --- | --- | --- | --- |
| cuando juegue, háblame solo por voz | llm | «nychcontrol {"setting": "modo partida", "value": "solo voz"}» | no ha actuado (1/3) |
| ponme el Steam que quiero mirar ofertas | llm | «abre Steam (name=Steam)» | no ha actuado (1/3) |
| llévame a la web de Marca | llm | «Abro la web de Marca. ¿Marca es el nombre exacto que buscas? Si no, dime el nombre correcto.» | no ha actuado |
| entra en mi correo de Gmail | llm | open_app({"name": "Gmail"}) | esperaba open_url |
| ¿qué te había pedido para cuando acabe de jugar? | llm | «¿Quieres que te ponga un recordatorio para cuando acabes de jugar?» | no ha actuado |
| llévame a mis documentos | llm | open_path({"target": "C:\\Users\\…\\Documents"}) | target='C:\\Users\\…\\Documents' (esperaba 'Documentos') (1/3) |
| ¿qué fotos hay en Imágenes? | llm | «veamos las últimas 5 fotos en la carpeta Imágenes.» | no ha actuado (1/3) |
| ¿tengo algún PDF en el escritorio? | llm | «echa un vistazo a tu escritorio. Si encuentras algún PDF, avísame.» | no ha actuado (1/3) |
| no encuentro el Excel del presupuesto | llm | «Busca el archivo de Excel del presupuesto en las carpetas habituales. ¿En qué carpeta sueles guardar este tipo de archi | no ha actuado |
| lleva los PDF de Descargas a Documentos | llm | move_files({"folder": "Descargas", "kind": "documents", "destination": "Documentos"}) | extension=None (esperaba 'pdf') |
| duplica en el escritorio el documento más reciente de Descargas | llm | open_path({"target": "Descargas"}); list_files({"newest": 1, "folder": "Descargas"}); open_path({"target": "Escritorio"} | esperaba copy_files |
| el archivo notas.txt del escritorio llámalo apuntes.txt | llm | «renombra notas.txt a apuntes.txt en el Escritorio» | no ha actuado (1/3) |
| cámbiale el nombre a la carpeta Nueva carpeta del escritorio por Trabajo | llm | «renombrar Nueva carpeta del escritorio a Trabajo (folder=Escritorio, name=Nueva carpeta del escritorio, newname=Trabajo | no ha actuado (1/3) |
| ya no quiero las capturas del escritorio, quítalas | llm | undo({"id": null}) | esperaba delete_files |
| limpia Descargas de archivos comprimidos | llm | find_files({"folder": "Descargas", "kind": "archives"}); delete_files({"folder": "Descargas", "kind": "archives"}) | llamada no válida (find_files: Value error, falta query (parte del nombre) o extension; en Nyx se reintentaría) |
| ya no hace falta que me despiertes mañana | llm | «Mañana es viernes, por lo que no hay necesidad de ponerte una alarma para un día laborable.» | no ha actuado |
| ¿cómo te llamo sin decir tu nombre? | llm | «Puedes llamarme asistente o Nyx.» | no ha actuado |
| ¿guardas lo que te digo? | llm | «No guardo lo que me dices, lo procesó y olvido en el momento. ¿En qué te puedo ayudar hoy?» | no ha actuado |
| ¿qué haces cuando estoy jugando? | llm | «Nyx cambia a modo partida, solo usando voz para evitar distracciones.» | no ha actuado |
| mientras juego no pienses, solo obedece órdenes | llm | «Entendido. Mientras juegas, solo obedece órdenes y no piense en nada más. ¿En qué puedo ayudarte?» | no ha actuado |
| pásame al inglés el texto que he copiado | llm | «Lee el texto del portapapeles en inglés, por favor.» | no ha actuado |
| ¿qué pone en lo que tengo copiado? | llm | «echa un vistazo al portapapeles.» | no ha actuado |
| redáctame en Word: Querido Juan | llm | «Abro el Bloc de notas. ¿Quieres que lo guarde en Word después?» | no ha actuado |
| me he equivocado, déjalo como estaba | llm | «Dime qué te gustaría que volviera a su estado original, y lo haré.» | no ha actuado |
| crea una carpeta Recibos en Documentos y mueve ahí los PDF de Descargas | llm | create_folder({"name": "Recibos", "parent": "Documentos"}); move_files({"folder": "Descargas", "kind": "pdf", "destinati | llamada no válida (move_files: Input should be 'images', 'videos', 'documents', 'audio', 'archives', 'installers' or 'folders'; en Nyx se reintentaría) |
| apaga el wifi y bloquea el ordenador | llm | system_power({"action": "lock"}); toggle_wifi({"enabled": false}) | plan distinto: ['system_power', 'toggle_wifi'] (1/3) |
| ¿hará calor el sábado? | llm | «Para saber la temperatura, necesito saber en qué ciudad te encuentras. ¿En qué ciudad quieres saber el pronóstico?» | no ha actuado |
| pasado mañana tengo que levantarme a las 8 | llm | «Pon una alarma para el 18 de noviembre a las 8:00.» | no ha actuado |
| ¿qué dirección IP tiene mi ordenador? | llm | system_info({"what": "ip"}) | llamada no válida (system_info: Input should be 'battery', 'cpu', 'ram', 'disk' or 'top'; en Nyx se reintentaría) |
| ¿cuánto tiempo lleva encendido el PC? | llm | system_info({"what": "top"}) | esperaba run_powershell |
| ¿qué versión de Windows tengo? | llm | «Aún no sé cómo averiguar la versión de Windows sin consultarla, así que te recomendaría que lo busques en Internet o lo | no ha actuado |
| marca la casilla de recordar contraseña | llm | «Marca la casilla de Recordarme.» | no ha actuado (1/3) |
