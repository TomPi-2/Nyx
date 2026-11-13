# Batería de frases · 2026-11-13 16:23

Modelo: `nyx-r1:7b`. Frases: 409. **Acierto: 379/409 (93 %)**.

Herramientas: todas (caben en su parte del contexto). Semilla del modelo: 1.

Primer token en lo que pasa por el LLM (primera pasada): mediana **665 ms**, media **735 ms**, peor 2440 ms.

| Camino | Frases | Acierto | Latencia mediana | Peor |
| --- | --- | --- | --- | --- |
| negativa | 7 | 7/7 | 0 ms | 0 ms |
| router | 267 | 267/267 | 0 ms | 6 ms |
| llm | 135 | 105/135 | 757 ms | 2877 ms |

## Fallos

| Frase | Camino | Qué hizo | Por qué |
| --- | --- | --- | --- |
| abre Spotify y maximízalo | llm | open_app({"name": "Spotify", "action": "maximize"}) | llamada no válida (open_app: Extra inputs are not permitted; en Nyx se reintentaría) (1/3) |
| ¿qué hora es? | llm | now_playing({}) | ha actuado |
| cuenta del 1 al 10 | llm | type_text({"text": "1 2 3 4 5 6 7 8 9 10"}) | ha actuado (1/3) |
| Crea tres archivos de texto | llm | create_folder({"name": "archivo1.txt", "parent": "el escritorio"}); create_folder({"name": "archivo2.txt", "parent": "el | ha actuado |
| entra en mi correo de Gmail | llm | open_app({"name": "Gmail"}) | esperaba open_url |
| ¿tengo algún PDF en el escritorio? | llm | find_files({"kind": "pdf", "folder": "el escritorio"}) | llamada no válida (find_files: Input should be 'images', 'videos', 'documents', 'audio', 'archives', 'installers' or 'folders'; en Nyx se reintentaría) |
| no encuentro el Excel del presupuesto | llm | open_path({"target": "excel presupuesto"}) | esperaba find_files |
| lleva los PDF de Descargas a Documentos | llm | move_files({"folder": "descargas", "destination": "documentos", "kind": "pdf"}) | llamada no válida (move_files: Input should be 'images', 'videos', 'documents', 'audio', 'archives', 'installers' or 'folders'; en Nyx se reintentaría) |
| pasa las capturas del escritorio a Imágenes | llm | move_files({"destination": "Imágenes", "kind": "screenshots"}) | llamada no válida (move_files: Field required; en Nyx se reintentaría) (1/3) |
| ya no quiero las capturas del escritorio, quítalas | llm | screenshot({"target": "current"}) | esperaba delete_files |
| ya no hace falta que me despiertes mañana | llm | set_alarm({"time": "07:00", "repeat": "none"}) | esperaba cancel_alarm |
| ¿cómo te llamo sin decir tu nombre? | llm | «Puedes llamarme Nyx. ¿En qué puedo ayudarte hoy, Nyx?» | no ha actuado |
| ¿guardas lo que te digo? | llm | save_note({"text": "Lo que me digas lo guardo"}) | llamada no válida (save_note: Field required; en Nyx se reintentaría) |
| ¿qué haces cuando estoy jugando? | llm | nyx_control({"setting": "modo partida", "value": "solo voz"}) | esperaba nyx_info |
| mientras juego no pienses, solo obedece órdenes | llm | pending({"action": "list"}) | esperaba nyx_control |
| pásame al inglés el texto que he copiado | llm | type_text({"text": "el texto que he copiado"}) | esperaba clipboard |
| redáctame en Word: Querido Juan | llm | open_app({"name": "Word"}) | esperaba type_text |
| abre el Excel y ponlo a la derecha | llm | open_app({"name": "Excel", "action": "next_monitor"}) | llamada no válida (open_app: Extra inputs are not permitted; en Nyx se reintentaría) (1/3) |
| crea una carpeta Recibos en Documentos y mueve ahí los PDF de Descargas | llm | create_folder({"name": "Recibos", "parent": "Documentos"}); move_files({"folder": "Descargas", "destination": "documento | llamada no válida (move_files: Input should be 'images', 'videos', 'documents', 'audio', 'archives', 'installers' or 'folders'; en Nyx se reintentaría) |
| apaga el wifi y bloquea el ordenador | llm | system_power({"action": "shutdown"}); toggle_wifi({"enabled": false}) | plan distinto: ['system_power', 'toggle_wifi'] |
| hola, ¿qué tal estás? | llm | nyx_info({"topic": "bienestar"}) | ha actuado (1/3) |
| ¿qué hora será ahora en Nueva York? | llm | web_search({"query": "hora actual en nueva york"}) | ha actuado (1/3) |
| manda un correo a mi jefe diciendo que llego tarde | llm | type_text({"app": "mail", "text": "Estimado/a [Nombre del jefe],\nLlego tarde hoy. [Razón].\nSaludos,\n[Tu nombre]"}) | ha actuado |
| pídeme una pizza | llm | media_control({"action": "pause", "music": true}) | ha actuado |
| publica en Instagram la última foto | llm | open_app({"name": "Instagram"}) | ha actuado |
| llama a mi hermano | llm | send_hotkey({"keys": "win+r"}) | ha actuado (1/3) |
| ¿cuánto tiempo lleva encendido el PC? | llm | system_info({"what": "top"}) | esperaba run_powershell |
| ¿qué versión de Windows tengo? | llm | system_info({"what": "version"}) | llamada no válida (system_info: Input should be 'battery', 'cpu', 'ram', 'disk' or 'top'; en Nyx se reintentaría) |
| necesito acordarme de llamar al fontanero, apúntalo en una nota | llm | save_note({"text": "llamar al fontanero"}) | llamada no válida (save_note: Field required; en Nyx se reintentaría) |
| explícame cómo funciona una vacuna | llm | nyx_info({"topic": "funcionamiento de una vacuna"}) | ha actuado (1/3) |
