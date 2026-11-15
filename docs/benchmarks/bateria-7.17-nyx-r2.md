# Batería de frases · 2026-11-15 15:55

Modelo: `nyx-r2:7b`. Frases: 409. **Acierto: 388/409 (95 %)**.

Herramientas: todas (caben en su parte del contexto). Semilla del modelo: 1.

Primer token en lo que pasa por el LLM (primera pasada): mediana **354 ms**, media **379 ms**, peor 1146 ms.

| Camino | Frases | Acierto | Latencia mediana | Peor |
| --- | --- | --- | --- | --- |
| negativa | 7 | 7/7 | 0 ms | 0 ms |
| router | 270 | 270/270 | 0 ms | 38 ms |
| llm | 132 | 111/132 | 429 ms | 2236 ms |

## Fallos

| Frase | Camino | Qué hizo | Por qué |
| --- | --- | --- | --- |
| vuelve atrás en el navegador | llm | undo({}) | esperaba app_action |
| entra en mi correo de Gmail | llm | «Aún no sé abrirte el correo. Puedo abrirte Gmail o el Panel de control. ¿Quieres que te abra Gmail?» | no ha actuado |
| está muy alto el sonido | llm | «Bajamos el volumen.» | no ha actuado |
| guárdame lo que se ve ahora mismo en la pantalla | llm | type_text({"app": "Bloc de notas", "text": "Lo que se ve ahora mismo en la pantalla"}) | esperaba screenshot (1/3) |
| ¿tengo algún PDF en el escritorio? | llm | find_files({"folder": "el escritorio", "kind": "documents"}) | llamada no válida (find_files: Value error, falta query (parte del nombre) o extension; en Nyx se reintentaría) (1/3) |
| no encuentro el Excel del presupuesto | llm | «Puedo abrirte Excel. ¿Dónde está el archivo? Si no lo encuentras, te lo abro yo y lo busco.» | no ha actuado |
| lleva los PDF de Descargas a Documentos | llm | move_files({"folder": "descargas", "destination": "documentos", "kind": "documents"}) | extension=None (esperaba 'pdf') (1/3) |
| pasa las capturas del escritorio a Imágenes | llm | move_files({"destination": "Imágenes"}) | llamada no válida (move_files: Field required; en Nyx se reintentaría) (1/3) |
| ya no quiero las capturas del escritorio, quítalas | llm | undo({}) | esperaba delete_files |
| ya no hace falta que me despiertes mañana | llm | «Aún no puedo hacer eso desde aquí. Si quieres, te lo envío yo.» | no ha actuado |
| ¿cómo te llamo sin decir tu nombre? | llm | «Puedes llamarme Nyx.» | no ha actuado |
| ¿guardas lo que te digo? | llm | «Sí, lo guardo. ¿Quieres que te lo repita?» | no ha actuado |
| ¿qué haces cuando estoy jugando? | llm | nyx_control({"value": "solo voz", "setting": "modo partida"}) | esperaba nyx_info |
| mientras juego no pienses, solo obedece órdenes | llm | nyx_control({"setting": "modo partida", "value": "solo voz"}) | setting='modo partida' (esperaba 'cerebro en partida') |
| pásame al inglés el texto que he copiado | llm | type_text({"app": "Bloc de notas", "text": "el texto que he copiado"}) | esperaba clipboard |
| abre el Excel y ponlo a la derecha | llm | open_app({"name": "Excel"}) | plan distinto: ['open_app'] (1/3) |
| silencia el Discord y sube la música | llm | media_control({"action": "pause", "music": true, "source": "discord"}) | plan distinto: ['media_control'] (1/3) |
| apaga el wifi y bloquea el ordenador | llm | system_power({"action": "shutdown"}); toggle_wifi({"enabled": false}) | plan distinto: ['system_power', 'toggle_wifi'] |
| ¿hará calor el sábado? | llm | «El sábado no sé cuánto calor hará. Puedes mirar luego.» | no ha actuado (1/3) |
| ¿cuánto tiempo lleva encendido el PC? | llm | system_info({"what": "top"}) | esperaba run_powershell |
| ¿qué versión de Windows tengo? | llm | «Windows 11 es la versión más reciente que tienes.» | no ha actuado |
