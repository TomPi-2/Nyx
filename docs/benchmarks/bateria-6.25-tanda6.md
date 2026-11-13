# Batería de frases · 2026-11-13 01:51

Modelo: `qwen2.5:7b`. Frases: 393. **Acierto: 364/393 (93 %)**.

Herramientas: todas (caben en su parte del contexto). Semilla del modelo: 1.

Primer token en lo que pasa por el LLM (primera pasada): mediana **505 ms**, media **583 ms**, peor 2542 ms.

| Camino | Frases | Acierto | Latencia mediana | Peor |
| --- | --- | --- | --- | --- |
| negativa | 7 | 7/7 | 0 ms | 0 ms |
| router | 255 | 255/255 | 0 ms | 7 ms |
| llm | 130 | 102/130 | 665 ms | 2543 ms |
| no_encontrado | 1 | 0/1 | 3 ms | 3 ms |

## Fallos

| Frase | Camino | Qué hizo | Por qué |
| --- | --- | --- | --- |
| entra en mi correo de Gmail | llm | open_app({"name": "Gmail"}) | esperaba open_url |
| ¿qué te había pedido para cuando acabe de jugar? | llm | «Cuando acabe de jugar, te pedí que solo funcione por voz.» | no ha actuado |
| pon algo para relajarme | llm | «Vĩnh tranquiliza-te.» | no ha actuado |
| ¿cuántos vídeos tengo en la carpeta de vídeos? | llm | «En la carpeta de vídeos hay 15 vídeos.» | no ha actuado |
| ¿tengo algún PDF en el escritorio? | llm | find_files({"folder": "Escritorio", "kind": "documents"}) | llamada no válida (find_files: Value error, falta query (parte del nombre) o extension; en Nyx se reintentaría) (1/3) |
| no encuentro el Excel del presupuesto | llm | «echa un vistazo a tu escritorio y a las carpetas de Trabajo y Documentos. Si no está allí, busca por todo el disco.» | no ha actuado |
| ¿tengo algún archivo que se llame curriculum? | llm | open_path({"target": "Escritorio"}) | esperaba find_files (1/3) |
| ábreme el último documento que descargué | no_encontrado | No encuentro «el ultimo documento que descargue» | no ha actuado |
| lleva los PDF de Descargas a Documentos | llm | move_files({"kind": "documents", "destination": "Documentos", "folder": "Descargas"}) | extension=None (esperaba 'pdf') |
| pasa las capturas del escritorio a Imágenes | llm | move_files({"names": ["Escritorio"], "destination": "Imágenes"}) | llamada no válida (move_files: Field required; en Nyx se reintentaría) |
| duplica en el escritorio el documento más reciente de Descargas | llm | open_path({"target": "Descargas"}); list_files({"folder": "Descargas", "newest": 1}); open_path({"target": "Escritorio"} | esperaba copy_files |
| cámbiale el nombre a la carpeta Nueva carpeta del escritorio por Trabajo | llm | «» | no ha actuado |
| ya no quiero las capturas del escritorio, quítalas | llm | «Desactivando el escritorio para que no haga capturas.» | no ha actuado |
| limpia Descargas de archivos comprimidos | llm | find_files({"folder": "Descargas", "kind": "archives"}); delete_files({"folder": "Descargas", "kind": "archives"}) | llamada no válida (find_files: Value error, falta query (parte del nombre) o extension; en Nyx se reintentaría) |
| a las 5 de la tarde tengo médico, avísame | llm | «pon una alarma para las 13:00.» | no ha actuado (1/3) |
| ya no hace falta que me despiertes mañana | llm | «no alarma» | no ha actuado (1/3) |
| ¿cómo te llamo sin decir tu nombre? | llm | «Así lo hago.» | no ha actuado |
| ¿guardas lo que te digo? | llm | «Ni guardo ni recuerdo conversaciones» | no ha actuado |
| ¿qué haces cuando estoy jugando? | llm | «Cuando estás jugando, solo respondo por voz y no muestro pantallas ni ventanas. Usaré solo comandos de voz para ayudart | no ha actuado |
| mientras juego no pienses, solo obedece órdenes | llm | «Entendido. Mientras juegas, solo obedezco órdenes sin pensar. ¿En qué puedo ayudarte?» | no ha actuado |
| léeme lo que copié antes | llm | «En voz alta diría: «El texto copiado es: [texto copiado]». ¿Quieres que lo escriba?» | no ha actuado (1/3) |
| pásame al inglés el texto que he copiado | llm | «En inglés, el texto que has copiado es: the text you copied.» | no ha actuado |
| redáctame en Word: Querido Juan | llm | «Abre Word y escribe: «Querido Juan».» | no ha actuado |
| vuelve a la página anterior | llm | «vuelve a la página anterior» | no ha actuado |
| me he equivocado, déjalo como estaba | llm | «Entendido. No haré cambios en el PC. Si quieres volver a la configuración anterior, avísame y lo haremos. ¿Necesitas al | no ha actuado |
| crea una carpeta Recibos en Documentos y mueve ahí los PDF de Descargas | llm | create_folder({"name": "Recibos", "parent": "Documentos"}); move_files({"folder": "Descargas", "kind": "pdf", "newest":  | llamada no válida (move_files: Input should be 'images', 'videos', 'documents', 'audio', 'archives', 'installers' or 'folders'; en Nyx se reintentaría) |
| apaga el wifi y bloquea el ordenador | llm | system_power({"action": "shutdown", "enabled": false}) | llamada no válida (system_power: Extra inputs are not permitted; en Nyx se reintentaría) |
| ¿hará calor el sábado? | llm | «Para saber si hará calor el sábado, necesito ver la previsión del tiempo.» | no ha actuado |
| pasado mañana tengo que levantarme a las 8 | llm | «setalarm a las 08:00 del día siguiente al día siguiente (time=08:00, day=tomorrow, repeat=none)» | no ha actuado |

## Notas (6.25, sexta tanda: órdenes con rodeos)

Con semilla (1), frente a la tanda 5 (343/385): **364/393 (93 %)**. **Router 255/255.**
En las 337 frases de la línea base de la 6.21: **310/337** (entonces 262).

- Reglas nuevas: `alarm_said` («mañana tengo que levantarme a las seis y media», «quiero que
  me despiertes a las 9 los fines de semana») y `timer_said` («la pasta tarda 12 minutos,
  avísame», «en un cuarto de hora tengo que salir, avísame», «cuenta tres minutos para el té»),
  que reescriben la frase a la forma que ya entiende la regla de siempre (`_as`);
  `files_said` («¿tengo algo en el escritorio?», «dime qué he descargado últimamente»),
  `brightness_said` («me deslumbra la pantalla», «la pantalla está muy oscura»), `focus_back`
  («vuelve al Visual Studio Code», solo con apps del equipo), `media_go_on` («sigue con la
  música»), `nyx_said` («¿dónde veo los atajos que has aprendido?», «cuando te escriba no me
  contestes hablando», «no te actives tan fácilmente») y abrir con explicación detrás
  («arranca el Discord que voy a hablar con los colegas», «abre lo del bluetooth para
  emparejar unos cascos»: si con la explicación no se encuentra y sin ella sí, sin ella).
- Tras la medida: `page_back` («vuelve a la página anterior», que el 7B escribe como texto y
  ahora el reencaminado ejecuta). Palabras nuevas en los grupos de herramientas (`groups.py`)
  para que las frases nuevas encuentren su grupo cuando no quepan todas (6.20b).
- 8 frases nuevas sin probar contra las reglas: 7 bien. «Pasado mañana tengo que levantarme a
  las 8» no lo entiende la regla (solo «mañana»), y el LLM se equivoca: queda para el LLM.
- Fallan ahora y no en la tanda 5: 3, todas por el LLM (variación).
