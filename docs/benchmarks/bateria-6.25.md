# Batería de frases · 2026-11-13 01:02

Modelo: `qwen2.5:7b`. Frases: 353. **Acierto: 281/353 (80 %)**.

Herramientas: todas (caben en su parte del contexto).

Primer token en lo que pasa por el LLM (primera pasada): mediana **497 ms**, media **551 ms**, peor 2658 ms.

| Camino | Frases | Acierto | Latencia mediana | Peor |
| --- | --- | --- | --- | --- |
| negativa | 7 | 7/7 | 0 ms | 0 ms |
| router | 164 | 161/164 | 0 ms | 7 ms |
| llm | 179 | 113/179 | 617 ms | 3201 ms |
| no_encontrado | 3 | 0/3 | 1 ms | 1 ms |

## Fallos

| Frase | Camino | Qué hizo | Por qué |
| --- | --- | --- | --- |
| arranca el Discord que voy a hablar con los colegas | no_encontrado | No encuentro «el discord que voy a hablar con los colegas» | no ha actuado |
| cierra el dis cord | router | close_app({"name": "dis cord"}) | name='dis cord' (esperaba 'Discord') |
| vuelve al Visual Studio Code | llm | open_app({"name": "Visual Studio Code"}) | esperaba focus_window |
| pon el Chrome en grande | llm | focus_window({"name": "Chrome"}) | esperaba window_layout |
| quita de en medio esta ventana | llm | close_app({"name": null}) | esperaba window_layout |
| minimisa el crome | llm | focus_window({"name": "Chrome", "action": "minimize"}) | llamada no válida (focus_window: Extra inputs are not permitted; en Nyx se reintentaría) |
| entra en mi correo de Gmail | llm | open_app({"name": "Gmail"}) | esperaba open_url |
| quiero cambiar el fondo de pantalla | llm | «En Windows, puedes cambiar el fondo de pantalla desde los Ajustes de Escritorio. ¿Te ayudo a abrirlos?» | no ha actuado |
| no me va el micrófono, llévame a donde se configura | llm | «Ve a los ajustes del audio para ver si el micrófono está activado y correctamente configurado.» | no ha actuado |
| abre lo del bluetooth para emparejar unos cascos | no_encontrado | No encuentro «lo del bluetooth para emparejar unos cascos» | no ha actuado |
| quiero cambiarte la voz | llm | nyx_control({"setting": "voz al escribir", "value": "más suave"}) | esperaba open_nyx_settings |
| ¿dónde veo los atajos que has aprendido? | llm | «En los ajustes de Nyx puedes ver y cambiar mis respuestas y otros parámetros, pero los atajos que aprendo los muestro c | no ha actuado |
| ¿qué te había pedido para cuando acabe de jugar? | llm | «Cuando acabes de jugar, quiero que vayas a tus ajustes de partida y pongas el modo solo voz.» | no ha actuado |
| ábreme lo de Pruebas Nyx | llm | open_app({"name": "Pruebas Nyx"}) | esperaba open_path |
| sube el bolumen | llm | «pon el volumen un poco más alto» | no ha actuado (1/3) |
| no veo nada, la pantalla está muy oscura | llm | «ilumina, aumenta el brillo» | no ha actuado (1/3) |
| vuelve a poner la canción de antes | llm | «reproduce de nuevo la última canción que estabas escuchando» | no ha actuado |
| pon algo para relajarme | llm | «pon el volumen al 20 y reproduce放松音乐» | no ha actuado |
| salta este vídeo de YouTube | llm | media_control({"action": "pause", "source": "youtube"}) | action='pause' (esperaba 'next') |
| ¿cómo se llama lo que estoy escuchando? | llm | «¿cómo se llama, qué se reproduce» | no ha actuado |
| ¿de quién es este tema? | llm | «Lo siento, no puedo ver el tema actual. ¿Podrías decirme de quién es si lo recuerdas?» | no ha actuado |
| ¿qué grupo es este? | llm | «Este es un grupo de metal. Sin más contexto, no puedo decirte el nombre, pero suelen incluir guitarras eléctricas, bate | no ha actuado |
| ¿tengo algo en el escritorio? | llm | «¿Tienes algo en el escritorio? Vamos a verlo.» | no ha actuado |
| dime qué he descargado últimamente | llm | «Veamos qué has descargado últimamente.» | no ha actuado |
| no encuentro el Excel del presupuesto | llm | «¿En qué carpeta sueles guardar el archivo? Puedo buscarlo en las últimas carpetas donde lo usas.» | no ha actuado |
| ¿tengo algún archivo que se llame curriculum? | llm | «Veamos si tienes algún archivo llamado Curriculum en las carpetas habituales. Abro Documentos y Descargas para buscarlo | no ha actuado |
| ábreme el último documento que descargué | no_encontrado | No encuentro «el ultimo documento que descargue» | no ha actuado |
| lleva los PDF de Descargas a Documentos | llm | move_files({"destination": "Documentos", "names": ["*.pdf"], "folder": "Descargas", "kind": "documents"}) | extension=None (esperaba 'pdf') |
| pasa las capturas del escritorio a Imágenes | llm | move_files({"destination": "Imágenes", "names": ["Escritorio"]}) | llamada no válida (move_files: Field required; en Nyx se reintentaría) |
| duplica en el escritorio el documento más reciente de Descargas | llm | open_path({"target": "Descargas"}); list_files({"folder": "Descargas", "newest": 1}); open_path({"target": "Escritorio"} | esperaba copy_files |
| cámbiale el nombre a la carpeta Nueva carpeta del escritorio por Trabajo | llm | «» | no ha actuado |
| ya no quiero las capturas del escritorio, quítalas | llm | open_settings({"page": "capturas"}) | esperaba delete_files |
| limpia Descargas de archivos comprimidos | llm | find_files({"folder": "Descargas", "kind": "archives"}) | llamada no válida (find_files: Value error, falta query (parte del nombre) o extension; en Nyx se reintentaría) |
| mañana tengo que levantarme a las seis y media | llm | «Pon una alarma para mañana a las 06:30.» | no ha actuado |
| quiero que me despiertes a las 9 los fines de semana | llm | «Pon una alarma para los fines de semana a las 9.» | no ha actuado |
| la pasta tarda 12 minutos, avísame cuando esté | llm | «Pon una alarma para 13:12.» | no ha actuado |
| en un cuarto de hora tengo que salir, avísame | llm | «Pon una alarma para dentro de cuarto de hora.» | no ha actuado |
| ¿a qué hora sonaba la alarma de mañana? | llm | «La alarma de mañana estaba programada para las 7:00.» | no ha actuado |
| ¿cuánto falta para que suene el temporizador? | llm | «echa un vistazo a la alarma de hoy.» | no ha actuado |
| ¿tengo algo programado? | llm | «Aún no sé hacer eso.» | no ha actuado |
| ¿me puedes decir cuánto falta para mi alarma? | llm | «Aún no has configurado ninguna alarma.» | no ha actuado |
| cronometra cuánto tardo en hacer esto | llm | «Empieza un cronómetro.» | no ha actuado |
| ya he terminado, para de contar el tiempo | llm | «Paremos el cronómetro. ¿Necesitas algo más?» | no ha actuado (1/3) |
| ¿cuánto marca el crono? | llm | «El cronómetro marca 01:00.» | no ha actuado |
| ¿cómo te llamo sin decir tu nombre? | llm | «simplemente / sin nombre específico No me llames por un nombre en particular, puedes llamarme directamente usando "¡Nyx | no ha actuado |
| ¿guardas lo que te digo? | llm | «grabación, guardo lo que me dices» | no ha actuado |
| ¿qué haces cuando estoy jugando? | llm | «En modo partida, solo respondo por voz y no muestro nada en pantalla.» | no ha actuado |
| cuando te escriba no me contestes hablando | llm | «no hablo, no contesto hablando» | no ha actuado |
| no te actives tan fácilmente | llm | «Entendido. No me activaré por ahora. ¿En qué puedo ayudarte hoy?» | no ha actuado |
| vivo en Sevilla | llm | «El tiempo en Sevilla lo consulto ahora.» | no ha actuado |
| mientras juego no pienses, solo obedece órdenes | llm | «Entendido. Mientras juegas, solo obedezco órdenes sin pensar. ¿En qué puedo ayudarte?» | no ha actuado |
| ¿tengo que coger chaqueta para salir? | llm | «[si llovera / no llovera] - Si llovera, coge chaqueta. Si no, ve sin chaqueta.» | no ha actuado |
| ¿qué tal día va a hacer mañana? | llm | «Mañana no va a llover, pero la temperatura será de 10 grados.» | no ha actuado |
| ¿hará bueno este finde en Valencia? | llm | «En Valencia, este fin de semana se espera tiempo nublado con posibilidad de lluvia. No parece que haga bueno.» | no ha actuado |
| ¿está nublado ahora? | llm | «Aún no sé cómo decir si está nublado sin ver el tiempo.» | no ha actuado |
| ¿cuántos grados va a hacer mañana en Barcelona? | llm | «Mañana en Barcelona tendrá una temperatura de 15 grados.» | no ha actuado |
| tengo frío, ¿qué temperatura hace fuera? | llm | «¿Qué ciudad te interesa saber?» | no ha actuado |
| ¿el ordenador va muy cargado? | llm | «consulta el uso de la CPU y la RAM {object <nil> <nil> [what] {"what":"cpu,ram"}}» | no ha actuado |
| ¿me queda sitio para instalar un juego de 100 gigas? | llm | «echa un vistazo a tu disco.» | no ha actuado |
| ¿por qué va tan lento el PC? | llm | «prüf den disco, ve el disco» | no ha actuado |
| ¿tengo el portátil enchufado? | llm | «echa un vistazo a laConfiguración de Windows/ajustes de alimentación para ver si el portátil está enchufado.» | no ha actuado |
| ¿cuánta memoria me queda libre? | llm | «Aún no sé cuánta memoria libre hay en tu PC.» | no ha actuado |
| ¿cuál de mis programas está gastando más memoria? | llm | system_info({"what": "ram"}) | what='ram' (esperaba 'top') |
| quítame internet un rato | llm | «Aún no sé hacer eso.» | no ha actuado |
| pásame al inglés el texto que he copiado | llm | «En inglés se dice text.» | no ha actuado |
| redáctame en Word: Querido Juan | llm | «Abro Word y te ayudo a redactar. ¿Dónde quieres que escriba?» | no ha actuado |
| pon la música en aleatorio | router | media_control({"action": "play", "source": "aleatorio"}) | esperaba app_action |
| busca en esta página la palabra precio | router | find_files({"query": "en esta pagina la palabra precio"}) | esperaba app_action/send_hotkey |
| acerca la página, que no veo la letra | llm | «-maximiza la página (si no está maximizada) o cambia a la ventana activa si la tienes oculta.» | no ha actuado |
| me he equivocado, déjalo como estaba | llm | «Entendido, mantendré todo como estaba. ¿Necesitas que haga algo más?» | no ha actuado |
| crea una carpeta Recibos en Documentos y mueve ahí los PDF de Descargas | llm | create_folder({"name": "Recibos", "parent": "Documentos"}); move_files({"kind": "pdf", "destination": "Documentos/Recibo | llamada no válida (move_files: Input should be 'images', 'videos', 'documents', 'audio', 'archives', 'installers' or 'folders'; en Nyx se reintentaría) |
| apaga el wifi y bloquea el ordenador | llm | system_power({"action": "shutdown", "enabled": false}) | llamada no válida (system_power: Extra inputs are not permitted; en Nyx se reintentaría) |

## Notas (6.25, primera tanda: abrir apps por lo que se necesita)

- Reglas nuevas en `core/nyx/brain/router/apps.py`: `open_game` («vamos a jugar al
  Valorant»), `open_task` («tengo que hacer una hoja de cálculo» → Excel o LibreOffice Calc),
  `open_with` («quiero grabar un vídeo con el OBS») y `open_need` («necesito la calculadora»).
  Solo abren si el nombre coincide **exacto** con una app o un juego del equipo; los nombres
  de apps de Windows que son palabras corrientes («ayuda», «tiempo», «notas»…) sin artículo no
  cuentan. Si no, la frase sigue yendo al LLM.
- Frases escritas antes que las reglas: 16 nuevas en la batería (todas bien) y 26 en
  `core/tests/test_router_apps.py` (12 que deben abrir y 14 que no).
- En las 337 frases de la línea base: **265/337** (antes 262). Arregladas por las reglas:
  «necesito la calculadora», «tengo que hacer una hoja de cálculo», «quiero grabar la pantalla
  con el OBS», «vamos a echar una partida al Fortnite». Las 6 que fallan ahora y antes no van
  todas por el LLM (el router da para ellas lo mismo que antes, comprobado con 1.632 frases):
  es la variación del modelo entre pasadas, no un fallo nuevo de las reglas.
- El primer token sale más lento que en la 6.21 (mediana 497 frente a 355 ms) sin haber
  tocado nada del LLM: variación de la gráfica en esta pasada. Se vigila en la siguiente.
