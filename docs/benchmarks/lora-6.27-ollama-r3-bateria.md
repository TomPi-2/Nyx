# Batería de frases · 2026-11-13 21:06

Modelo: `nyx-r3:7b`. Frases: 409. **Acierto: 392/409 (96 %)**.

Herramientas: todas (caben en su parte del contexto). Semilla del modelo: 1.

Primer token en lo que pasa por el LLM (primera pasada): mediana **355 ms**, media **382 ms**, peor 976 ms.

| Camino | Frases | Acierto | Latencia mediana | Peor |
| --- | --- | --- | --- | --- |
| negativa | 7 | 7/7 | 0 ms | 0 ms |
| router | 267 | 267/267 | 0 ms | 35 ms |
| llm | 135 | 118/135 | 422 ms | 1995 ms |

## Fallos

| Frase | Camino | Qué hizo | Por qué |
| --- | --- | --- | --- |
| abre Spotify y maximízalo | llm | open_app({"name": "Spotify", "action": "maximize"}) | llamada no válida (open_app: Extra inputs are not permitted; en Nyx se reintentaría) (1/3) |
| quiero escuchar música en Spotify | llm | open_url({"target": "Spotify"}) | esperaba open_app/media_control |
| ¿tengo algún PDF en el escritorio? | llm | find_files({"folder": "Escritorio", "kind": "documents"}) | llamada no válida (find_files: Value error, falta query (parte del nombre) o extension; en Nyx se reintentaría) (1/3) |
| no encuentro el Excel del presupuesto | llm | open_path({"target": "presupuesto"}) | esperaba find_files |
| ya no quiero las capturas del escritorio, quítalas | llm | screenshot({"target": "current"}) | esperaba delete_files |
| ¿cómo te llamo sin decir tu nombre? | llm | «Te llamo Nyx.» | no ha actuado |
| ¿guardas lo que te digo? | llm | «Sí, lo guardo. ¿Dime qué quieres que guarde?» | no ha actuado |
| ¿qué haces cuando estoy jugando? | llm | «En modo partida, solo respondo por voz y no abro nada ni muevo ventanas.» | no ha actuado |
| mientras juego no pienses, solo obedece órdenes | llm | nyx_control({"setting": "modo partida", "value": "solo voz"}) | setting='modo partida' (esperaba 'cerebro en partida') |
| pásame al inglés el texto que he copiado | llm | clipboard({"action": "read"}); type_text({"app": "Bloc de notas", "text": "el texto que has copiado"}) | esperaba clipboard |
| silencia el Discord y sube la música | llm | set_volume({"mute": true, "music": true, "app": "Discord"}) | llamada no válida (set_volume: Extra inputs are not permitted; en Nyx se reintentaría) |
| crea una carpeta Recibos en Documentos y mueve ahí los PDF de Descargas | llm | create_folder({"name": "Recibos", "parent": "Documentos"}); move_files({"folder": "Descargas", "kind": "pdf", "destinati | llamada no válida (move_files: Input should be 'images', 'videos', 'documents', 'audio', 'archives', 'installers' or 'folders'; en Nyx se reintentaría) |
| apaga el wifi y bloquea el ordenador | llm | system_power({"action": "shutdown"}); toggle_wifi({"enabled": false}) | plan distinto: ['system_power', 'toggle_wifi'] |
| ¿qué hora será ahora en Nueva York? | llm | get_weather({"city": "Nueva York"}) | ha actuado |
| ¿cuánto tiempo lleva encendido el PC? | llm | system_info({"what": "top"}) | esperaba run_powershell |
| ¿qué versión de Windows tengo? | llm | «Aún no sé buscar en internet. Puedo abrirte la web para que lo busques tú.» | no ha actuado |
| necesito acordarme de llamar al fontanero, apúntalo en una nota | llm | save_note({"text": "llamar al fontanero"}) | llamada no válida (save_note: Field required; en Nyx se reintentaría) (1/3) |
