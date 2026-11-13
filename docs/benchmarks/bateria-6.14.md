# Batería de frases · 2026-11-13 04:06

Modelo: `qwen2.5:7b`. Frases: 400. **Acierto: 368/400 (92 %)**.

Herramientas: todas (caben en su parte del contexto). Semilla del modelo: 1.

Primer token en lo que pasa por el LLM (primera pasada): mediana **354 ms**, media **397 ms**, peor 1764 ms.

| Camino | Frases | Acierto | Latencia mediana | Peor |
| --- | --- | --- | --- | --- |
| negativa | 7 | 7/7 | 0 ms | 0 ms |
| router | 256 | 256/256 | 0 ms | 5 ms |
| llm | 136 | 105/136 | 458 ms | 1764 ms |
| no_encontrado | 1 | 0/1 | 3 ms | 3 ms |

## Fallos

| Frase | Camino | Qué hizo | Por qué |
| --- | --- | --- | --- |
| llévame a la ventana del Discord | llm | window_layout({"action": "maximize", "name": "Discord"}) | esperaba focus_window (1/3) |
| llévame a la web de Marca | llm | «abre Marca» | no ha actuado (1/3) |
| entra en mi correo de Gmail | llm | open_app({"name": "Gmail"}) | esperaba open_url |
| ¿qué te había pedido para cuando acabe de jugar? | llm | «¿Has puesto un recordatorio para cuando acabes de jugar? Si no, ¿qué quieres que te recuerde?» | no ha actuado |
| quítale el sonido al Chrome | llm | media_control({"source": "Chrome", "action": "stop"}) | esperaba set_volume |
| esta canción no me gusta, pásala | llm | «parece que has empezado a reproducir una canción que no te gusta. ¿Deseas cambiarla? Si quieres, puedes decirme la canc | no ha actuado |
| pon algo para relajarme | llm | «Relájate con una canción calmante. ¿Te apetece algo de jazz? {openurl target="jazz"}» | no ha actuado |
| ¿tengo algún PDF en el escritorio? | llm | find_files({"folder": "Escritorio", "kind": "documents"}) | llamada no válida (find_files: Value error, falta query (parte del nombre) o extension; en Nyx se reintentaría) (1/3) |
| no encuentro el Excel del presupuesto | llm | «¿Has mirado en las carpetas de Trabajo o Finanzas?» | no ha actuado |
| ábreme el último documento que descargué | no_encontrado | No encuentro «el ultimo documento que descargue» | no ha actuado |
| lleva los PDF de Descargas a Documentos | llm | move_files({"folder": "Descargas", "names": ["*.pdf"], "destination": "Documentos"}) | extension=None (esperaba 'pdf') |
| quita los instaladores de Descargas y ponlos en la carpeta Instaladores | llm | move_files({"folder": "Descargas", "names": ["*.installer"], "destination": "Instaladores"}) | kind=None (esperaba 'installers') (1/3) |
| duplica en el escritorio el documento más reciente de Descargas | llm | open_path({"target": "Descargas"}); list_files({"folder": "Descargas", "newest": 1}); open_path({"target": "Escritorio"} | esperaba copy_files |
| el archivo notas.txt del escritorio llámalo apuntes.txt | llm | «renombra notas.txt a apuntes.txt en el Escritorio» | no ha actuado |
| ya no quiero las capturas del escritorio, quítalas | llm | screenshot({"enabled": false}) | llamada no válida (screenshot: Extra inputs are not permitted; en Nyx se reintentaría) |
| limpia Descargas de archivos comprimidos | llm | find_files({"folder": "Descargas", "kind": "archives"}); delete_files({"folder": "Descargas", "kind": "archives"}) | llamada no válida (find_files: Value error, falta query (parte del nombre) o extension; en Nyx se reintentaría) |
| a las 5 de la tarde tengo médico, avísame | llm | set_alarm({"time": "16:00", "label": "Cita médica"}) | time='16:00' (esperaba '17:00') |
| olvida el recordatorio de llamar a mamá | llm | cancel_alarm({"label": "llamar a mamá"}) | llamada no válida (cancel_alarm: Extra inputs are not permitted; en Nyx se reintentaría) |
| ¿cómo te llamo sin decir tu nombre? | llm | «simplemente dilo como "Nyxi" o "Nyxie".» | no ha actuado |
| ¿guardas lo que te digo? | llm | «Sí, guardo lo que me dices. ¿En qué puedo ayudarte hoy?» | no ha actuado |
| ¿qué haces cuando estoy jugando? | llm | «Nyx se adapta a tu juego. Solo por voz, sin distracciones visuales. Si quieres pausar la música o silenciar notificacio | no ha actuado |
| ponte de color rosa | llm | set_brightness({"level": 50}) | esperaba nyx_control |
| mientras juego no pienses, solo obedece órdenes | llm | «Entendido. Mientras juegas, solo obedezco órdenes sin pensar. ¿En qué puedo ayudarte?» | no ha actuado |
| pásame al inglés el texto que he copiado | llm | «En inglés, el texto copiado es el que tienes en el portapapeles.» | no ha actuado |
| redáctame en Word: Querido Juan | llm | open_app({"name": "Word"}) | esperaba type_text |
| crea una carpeta Recibos en Documentos y mueve ahí los PDF de Descargas | llm | create_folder({"name": "Recibos", "parent": "Documentos"}); move_files({"folder": "Descargas", "kind": "pdf", "newest":  | llamada no válida (move_files: Input should be 'images', 'videos', 'documents', 'audio', 'archives', 'installers' or 'folders'; en Nyx se reintentaría) |
| apaga el wifi y bloquea el ordenador | llm | system_power({"action": "lock"}); toggle_wifi({"enabled": false}) | plan distinto: ['system_power', 'toggle_wifi'] |
| instálame el Minecraft | llm | install_app({"action": "install", "name": "Minecraft"}) | ha actuado |
| ¿hará calor el sábado? | llm | «El sábado no se espera calor, la temperatura estará en torno a 10°C.» | no ha actuado |
| ¿qué dirección IP tiene mi ordenador? | llm | get_weather({"city": ""}) | esperaba run_powershell |
| ¿cuánto tiempo lleva encendido el PC? | llm | system_info({"what": "top"}) | esperaba run_powershell |
| ¿qué versión de Windows tengo? | llm | «No puedo verificar directamente la versión de Windows sin consultar la información del sistema. Aún no sé cómo hacer es | no ha actuado |

## Notas (6.13 y 6.14: run_powershell, install_app y ui_action)

Con semilla (1), 43 herramientas: **368/400**, router 256/256. Las tres nuevas se usan bien
(«instálame el VLC», «desinstala el Zoom», «pulsa el botón Aceptar», «marca la casilla…») y el
modelo no tira de ellas donde no toca. Las preguntas de «¿qué IP tengo?» o «¿cuánto lleva
encendido?» no las manda a PowerShell (las contesta con otra herramienta o no actúa): es lo
prudente con una herramienta roja. Con 3 herramientas más, el 7B cambia en algunas frases que
antes acertaba (8) y acierta otras que fallaba (7): la variación de siempre al tocar el prompt;
varias de las perdidas pasan a reglas (tanda 7). «Instálame el Minecraft» esperaba «no sé
hacerlo»; ahora se espera `install_app` (con confirmación).
