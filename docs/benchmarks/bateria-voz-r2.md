# Batería de frases · 2026-11-16 00:08

Modelo: `nyx-r2:7b`. Frases: 427. **Acierto: 410/427 (96 %)**.

Herramientas: todas (caben en su parte del contexto). Semilla del modelo: 1.

Primer token en lo que pasa por el LLM (primera pasada): mediana **379 ms**, media **408 ms**, peor 1013 ms.

| Camino | Frases | Acierto | Latencia mediana | Peor |
| --- | --- | --- | --- | --- |
| negativa | 7 | 7/7 | 0 ms | 0 ms |
| router | 283 | 283/283 | 0 ms | 6 ms |
| llm | 137 | 120/137 | 452 ms | 1823 ms |

## Fallos

| Frase | Camino | Qué hizo | Por qué |
| --- | --- | --- | --- |
| crea la carpeta Fondos en Imágenes y mueve allí las fotos de Descargas | llm | create_folder({"name": "Fondos", "parent": "Imágenes"}); move_files({"destination": "Carpeta/Subcarpeta", "names": ["fot | llamada no válida (move_files: Field required; en Nyx se reintentaría) (1/3) |
| entra en mi correo de Gmail | llm | «Aún no sé abrirte el correo. Puedo abrirte Gmail o el panel de control. ¿Quieres que te lo abra?» | no ha actuado |
| está muy alto el sonido | llm | «Voy a bajarlo un poco.» | no ha actuado |
| guárdame lo que se ve ahora mismo en la pantalla | llm | type_text({"app": "Bloc de notas", "text": "Lo que se ve ahora mismo en la pantalla"}) | esperaba screenshot |
| ¿tengo algún PDF en el escritorio? | llm | find_files({"folder": "el escritorio", "kind": "documents"}) | llamada no válida (find_files: Value error, falta query (parte del nombre) o extension; en Nyx se reintentaría) (1/3) |
| no encuentro el Excel del presupuesto | llm | «Puedo abrirte Excel. ¿Quieres que lo haga?» | no ha actuado |
| ya no quiero las capturas del escritorio, quítalas | llm | undo({}) | esperaba delete_files |
| ¿cómo te llamo sin decir tu nombre? | llm | «Puedes llamarme Nyx.» | no ha actuado |
| ¿guardas lo que te digo? | llm | «Aún no sé guardar archivos. Si quieres, te abro el Bloc de notas y lo escribes tú.» | no ha actuado |
| ¿qué haces cuando estoy jugando? | llm | nyx_control({"setting": "modo partida", "value": "solo voz"}) | esperaba nyx_info |
| mientras juego no pienses, solo obedece órdenes | llm | nyx_control({"setting": "modo partida", "value": "solo voz"}) | setting='modo partida' (esperaba 'cerebro en partida') |
| pásame al inglés el texto que he copiado | llm | «Aún no sé copiar ni pegar. Puedo abrirte la app para que lo hagas tú.» | no ha actuado |
| abre el Excel y ponlo a la derecha | llm | open_app({"name": "Excel"}) | plan distinto: ['open_app'] (1/3) |
| silencia el Discord y sube la música | llm | set_volume({"app": "discord", "mute": true, "music": true}) | llamada no válida (set_volume: Extra inputs are not permitted; en Nyx se reintentaría) (1/3) |
| apaga el wifi y bloquea el ordenador | llm | system_power({"action": "shutdown"}); toggle_wifi({"enabled": false}) | plan distinto: ['system_power', 'toggle_wifi'] |
| ¿cuánto tiempo lleva encendido el PC? | llm | system_info({"what": "top"}) | esperaba run_powershell |
| ¿qué versión de Windows tengo? | llm | «Windows 11 es la versión más reciente que tienes.» | no ha actuado |
