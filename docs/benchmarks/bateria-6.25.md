# Batería de frases · 2026-11-13 01:11

Modelo: `qwen2.5:7b`. Frases: 361. **Acierto: 285/361 (79 %)**.

Herramientas: todas (caben en su parte del contexto).

Primer token en lo que pasa por el LLM (primera pasada): mediana **438 ms**, media **545 ms**, peor 2653 ms.

| Camino | Frases | Acierto | Latencia mediana | Peor |
| --- | --- | --- | --- | --- |
| negativa | 7 | 7/7 | 0 ms | 0 ms |
| router | 175 | 172/175 | 0 ms | 7 ms |
| llm | 176 | 106/176 | 639 ms | 2653 ms |
| no_encontrado | 3 | 0/3 | 2 ms | 2 ms |

## Fallos

| Frase | Camino | Qué hizo | Por qué |
| --- | --- | --- | --- |
| arranca el Discord que voy a hablar con los colegas | no_encontrado | No encuentro «el discord que voy a hablar con los colegas» | no ha actuado |
| cierra el dis cord | router | close_app({"name": "dis cord"}) | name='dis cord' (esperaba 'Discord') |
| enséñame el Spotify que lo tengo abierto | llm | «Spotify ya está abierto. ¿Quieres que lo traiga al frente?» | no ha actuado (1/3) |
| vuelve al Visual Studio Code | llm | «Traigo al frente Visual Studio Code.» | no ha actuado |
| entra en mi correo de Gmail | llm | open_app({"name": "Gmail"}) | esperaba open_url |
| quiero cambiar el fondo de pantalla | llm | «Pon el nuevo fondo de pantalla que prefieras. Si tienes una imagen en mente, puedes decirme su nombre o ubicación.» | no ha actuado |
| no me va el micrófono, llévame a donde se configura | llm | «Ve a los ajustes del micrófono para comprobar si está habilitado y ajustar el nivel de volumen de entrada.» | no ha actuado |
| abre lo del bluetooth para emparejar unos cascos | no_encontrado | No encuentro «lo del bluetooth para emparejar unos cascos» | no ha actuado |
| quiero cambiarte la voz | llm | «Para cambiar la velocidad de mi voz, necesito que me digas si quieres que lo hagas más rápida o más lenta.» | no ha actuado |
| ¿dónde veo los atajos que has aprendido? | llm | «En los Ajustes de Nyx puedes ver y cambiar mis respuestas y comportamientos.» | no ha actuado |
| ¿qué te había pedido para cuando acabe de jugar? | llm | «Cuando acabes de jugar, solo te escucharé por voz.» | no ha actuado |
| ábreme lo de Pruebas Nyx | llm | open_app({"name": "Pruebas Nyx"}) | esperaba open_path |
| el Discord se oye demasiado fuerte | llm | «baja el volumen de Discord a un 30.» | no ha actuado |
| sube el bolumen | llm | «pon el volumen un poco más alto» | no ha actuado |
| me deslumbra la pantalla | llm | «reduce brightness, disminuye el brillo» | no ha actuado (1/3) |
| no veo nada, la pantalla está muy oscura | llm | «baja el brillo {change=-20}» | no ha actuado |
| vuelve a poner la canción de antes | llm | «reproduce la última canción que estabas escuchando» | no ha actuado |
| pon algo para relajarme | llm | «pon la música de fondo relajante en YouTube» | no ha actuado |
| salta este vídeo de YouTube | llm | media_control({"action": "pause", "source": "youtube"}) | action='pause' (esperaba 'next') |
| ¿cómo se llama lo que estoy escuchando? | llm | «¿cómo se llama, qué se está reproduciendo» | no ha actuado |
| ¿de quién es este tema? | llm | «Lo siento, no puedo ver el tema actual. ¿Podrías decirme de quién es si lo recuerdas?» | no ha actuado |
| ¿qué grupo es este? | llm | «Este término es muy amplio, pero generalmente se refiere a una banda o conjunto de músicos que interpretan música. Si t | no ha actuado |
| ¿tengo algo en el escritorio? | llm | «echa un vistazo al escritorio.» | no ha actuado |
| ¿qué fotos hay en Imágenes? | llm | open_path({"target": "Imágenes"}) | esperaba list_files/find_files (1/3) |
| dime qué he descargado últimamente | llm | «He buscado en las últimas descargas y no has descargado nada recientemente. ¿Necesitas buscar algo en particular?» | no ha actuado |
| ¿tengo algún PDF en el escritorio? | llm | find_files({"folder": "Escritorio", "kind": "documents"}) | llamada no válida (find_files: Value error, falta query (parte del nombre) o extension; en Nyx se reintentaría) (1/3) |
| no encuentro el Excel del presupuesto | llm | «¿En qué carpeta sueles guardar el archivo de Excel del presupuesto?» | no ha actuado |
| ¿tengo algún archivo que se llame curriculum? | llm | «Veamos si tienes algún archivo llamado Curriculum en las carpetas habituales. Abro Documentos y Descargas.» | no ha actuado (1/3) |
| ábreme el último documento que descargué | no_encontrado | No encuentro «el ultimo documento que descargue» | no ha actuado |
| lleva los PDF de Descargas a Documentos | llm | move_files({"kind": "documents", "destination": "Documentos", "names": [], "folder": "Descargas"}) | extension=None (esperaba 'pdf') |
| pasa las capturas del escritorio a Imágenes | llm | move_files({"destination": "Imágenes", "names": ["Escritorio"]}) | llamada no válida (move_files: Field required; en Nyx se reintentaría) (1/3) |
| duplica en el escritorio el documento más reciente de Descargas | llm | open_path({"target": "Descargas"}); list_files({"folder": "Descargas", "newest": 1}); open_path({"target": "Escritorio"} | esperaba copy_files |
| cámbiale el nombre a la carpeta Nueva carpeta del escritorio por Trabajo | llm | «» | no ha actuado (1/3) |
| ya no quiero las capturas del escritorio, quítalas | llm | open_settings({"page": "capturas"}) | esperaba delete_files |
| limpia Descargas de archivos comprimidos | llm | find_files({"folder": "Descargas", "kind": "archives"}) | llamada no válida (find_files: Value error, falta query (parte del nombre) o extension; en Nyx se reintentaría) |
| mañana tengo que levantarme a las seis y media | llm | «Poné una alarma para mañana a las 6:30.» | no ha actuado |
| quiero que me despiertes a las 9 los fines de semana | llm | «Pon una alarma para los fines de semana a las 9.» | no ha actuado |
| a las 5 de la tarde tengo médico, avísame | llm | «[setalarm {"time": "13:00", "label": "medio médico"}]» | no ha actuado |
| la pasta tarda 12 minutos, avísame cuando esté | llm | «Pon una alarma para 13:20 del 13 de noviembre.» | no ha actuado |
| en un cuarto de hora tengo que salir, avísame | llm | «Pon una alarma para las 01:23.» | no ha actuado |
| ¿a qué hora sonaba la alarma de mañana? | llm | «La alarma de mañana está puesta para las 07:00.» | no ha actuado |
| ¿cuánto falta para que suene el temporizador? | llm | «Si no hay temporizadores, no falta nada. Si hay, te diré cuánto tiempo queda.» | no ha actuado |
| ¿tengo algo programado? | llm | «echa un vistazo a tus alarmas y recordatorios.» | no ha actuado |
| ¿me puedes decir cuánto falta para mi alarma? | llm | «Aún no sé cuánto falta para tu alarma, necesito saber qué hora está puesta. ¿Podrías decírmela?» | no ha actuado |
| cronometra cuánto tardo en hacer esto | llm | «[¿cuánto lleva? / para el cronómetro]» | no ha actuado (1/3) |
| ya he terminado, para de contar el tiempo | llm | «Paremos el cronómetro. ¿Necesitas algo más?» | no ha actuado (1/3) |
| ¿cuánto marca el crono? | llm | «¿Cuánto lleva el cronómetro?» | no ha actuado |
| ¿cómo te llamo sin decir tu nombre? | llm | «simplemente / sin nombre Sin decir mi nombre, puedes llamarme así: "¡Vale!" o "¡Eh!".» | no ha actuado |
| ¿guardas lo que te digo? | llm | «Aún no sé grabar conversaciones.» | no ha actuado |
| ¿qué haces cuando estoy jugando? | llm | «Cuando estás jugando, Nyx solo responde por voz y no muestra ventanas ni texto.» | no ha actuado |
| cuando te escriba no me contestes hablando | llm | «Entendido. Ahora estaré en modo texto sin hablar.» | no ha actuado |
| no te actives tan fácilmente | llm | «no me altere, no te pongas nervioso» | no ha actuado |
| vivo en Sevilla | llm | «Sevilla es la capital de la comunidad autónoma de Andalucía.» | no ha actuado |
| mientras juego no pienses, solo obedece órdenes | llm | «Entendido. Mientras juegas, solo obedezca órdenes sin pensar. ¿En qué puedo ayudarte?» | no ha actuado |
| ¿tengo que coger chaqueta para salir? | llm | «[si llovera / no llovera] - Si llovera, coge chaqueta; si no, no la necesitas.» | no ha actuado |
| ¿qué tal día va a hacer mañana? | llm | «Mañana no va a llover, se espera un día soleado.» | no ha actuado |
| ¿hará bueno este finde en Valencia? | llm | «El tiempo para este fin de semana en Valencia será parcialmente nublado con temperaturas entre 15 y 20 grados. No hay p | no ha actuado |
| ¿está nublado ahora? | llm | «Aún no sé cómo decir si está nublado sin consultar, así que verifica en una app de tiempo.» | no ha actuado |
| ¿cuántos grados va a hacer mañana en Barcelona? | llm | «Mañana en Barcelona hará 15 grados.» | no ha actuado |
| tengo frío, ¿qué temperatura hace fuera? | llm | «¿Qué ciudad te interesa saber? Si no especificas, te daré la información de la ciudad configurada en ajustes.» | no ha actuado |
| ¿el ordenador va muy cargado? | llm | «echa un vistazo al uso de la CPU y la RAM.» | no ha actuado |
| ¿me queda sitio para instalar un juego de 100 gigas? | llm | «echa un vistazo a tu disco para ver cuánto espacio tienes.» | no ha actuado |
| ¿por qué va tan lento el PC? | llm | «Primero, veamos qué está usando más la CPU y si hay espacio en el disco.» | no ha actuado |
| ¿tengo el portátil enchufado? | llm | «consulta la información del sistema / ¿cuánta batería uso?» | no ha actuado |
| ¿cuánta memoria me queda libre? | llm | «Aún no sé cuánta memoria libre tienes.» | no ha actuado |
| ¿cuál de mis programas está gastando más memoria? | llm | system_info({"what": "ram"}) | what='ram' (esperaba 'top') |
| quítame internet un rato | llm | «Aún no sé cómo quitar la conexión a internet temporalmente.» | no ha actuado |
| pásame al inglés el texto que he copiado | llm | «En inglés, tu texto es text.» | no ha actuado |
| redáctame en Word: Querido Juan | llm | «Abro el Bloc de Notas, pero Word es mejor para este trabajo. Abriré Word ahora.» | no ha actuado |
| pon la música en aleatorio | router | media_control({"action": "play", "source": "aleatorio"}) | esperaba app_action |
| busca en esta página la palabra precio | router | find_files({"query": "en esta pagina la palabra precio"}) | esperaba app_action/send_hotkey |
| vuelve a la página anterior | llm | «vuelve a la página anterior» | no ha actuado (1/3) |
| acerca la página, que no veo la letra | llm | «-maximiza la página (si está en un navegador) o usa el zoom (si es una app)» | no ha actuado |
| me he equivocado, déjalo como estaba | llm | «reinicia la partida, restart» | no ha actuado |
| crea una carpeta Recibos en Documentos y mueve ahí los PDF de Descargas | llm | create_folder({"name": "Recibos", "parent": "Documentos"}); move_files({"newest": 5, "destination": "Documentos/Recibos" | llamada no válida (move_files: Input should be 'images', 'videos', 'documents', 'audio', 'archives', 'installers' or 'folders'; en Nyx se reintentaría) |
| apaga el wifi y bloquea el ordenador | llm | system_power({"enabled": false, "action": "shutdown"}) | llamada no válida (system_power: Extra inputs are not permitted; en Nyx se reintentaría) |

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

## Notas (6.25, segunda tanda: ventanas dichas de otra forma)

Este informe es el de después de la segunda tanda (361 frases).

- Reglas nuevas en `core/nyx/brain/router/ventanas.py`: `window_big` y `window_bigger` («pon el
  Chrome en grande», «haz más grande esta ventana»), `window_away` («quita de en medio esta
  ventana», «aparta el Chrome», «manda Spotify abajo») y `window_back` («vuelve a poner el
  Chrome como estaba»). Solo si lo nombrado es esta ventana, una ventana o una app del equipo
  («haz más grande la letra» o «quita de en medio los archivos» siguen yendo al LLM).
  `window_state` entiende «minimisa»/«maximisa» y corrige nombres mal oídos («crome» → Google
  Chrome) solo si se parecen letra a letra: «navegador» sigue siendo el predeterminado.
- 8 frases nuevas en la batería (todas bien) y 18 en `core/tests/test_router_ventanas.py`.
- Router: **172/175** (los 3 fallos son los de la 6.17, que van a la tanda de `ERRORES.md`).
  Arregladas en la línea base: «pon el Chrome en grande», «quita de en medio esta ventana»,
  «minimisa el crome». En las 337 de la línea base: **261** (262 en la 6.21): las reglas de
  las dos tandas arreglan 7 frases (las 4 de la primera y estas 3) y el LLM, en esta pasada,
  arregla 3 y pierde 11. Con la primera tanda salió 265.
- El LLM varía entre pasadas (106–116/185 en estas tres medidas con las mismas frases y el
  mismo prompt): las frases que fallan ahora y no antes van todas por el LLM y antes salían
  2 de 3. Por eso la regla de la 0.3 se mira frase a frase en lo que resuelve el router, que es
  determinista. Pendiente para una tanda de sonido: «baja el volumen de Discord a un 30»
  (lo escribe el 7B y el router no lo entiende).
