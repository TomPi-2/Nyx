# Batería de frases · 2026-11-13 01:46

Modelo: `qwen2.5:7b`. Frases: 385. **Acierto: 343/385 (89 %)**.

Herramientas: todas (caben en su parte del contexto). Semilla del modelo: 1.

Primer token en lo que pasa por el LLM (primera pasada): mediana **525 ms**, media **573 ms**, peor 2575 ms.

| Camino | Frases | Acierto | Latencia mediana | Peor |
| --- | --- | --- | --- | --- |
| negativa | 7 | 7/7 | 0 ms | 0 ms |
| router | 231 | 231/231 | 0 ms | 7 ms |
| llm | 144 | 105/144 | 634 ms | 2575 ms |
| no_encontrado | 3 | 0/3 | 1 ms | 2 ms |

## Fallos

| Frase | Camino | Qué hizo | Por qué |
| --- | --- | --- | --- |
| arranca el Discord que voy a hablar con los colegas | no_encontrado | No encuentro «el discord que voy a hablar con los colegas» | no ha actuado |
| vuelve al Visual Studio Code | llm | open_app({"name": "Visual Studio Code"}) | esperaba focus_window (1/3) |
| entra en mi correo de Gmail | llm | open_app({"name": "Gmail"}) | esperaba open_url |
| abre lo del bluetooth para emparejar unos cascos | no_encontrado | No encuentro «lo del bluetooth para emparejar unos cascos» | no ha actuado |
| ¿dónde veo los atajos que has aprendido? | llm | «Puedes ver mis atajos y ajustes en los Ajustes de Nyx.» | no ha actuado |
| ¿qué te había pedido para cuando acabe de jugar? | llm | «Veamos, ¿qué tenías pendiente después de jugar?» | no ha actuado |
| enséñame la carpeta de las descargas | llm | «Abro la carpeta de descargas.» | no ha actuado (1/3) |
| ábreme lo de Pruebas Nyx | llm | open_app({"name": "Pruebas Nyx"}) | esperaba open_path |
| no veo nada, la pantalla está muy oscura | llm | «aumenta la luz del monitor» | no ha actuado |
| sigue con la música | llm | «-mediacontrol: play» | no ha actuado (1/3) |
| pon algo para relajarme | llm | «Pon la música relajante.» | no ha actuado |
| ¿tengo algo en el escritorio? | llm | «echa un vistazo al escritorio.» | no ha actuado |
| dime qué he descargado últimamente | llm | «Veamos qué has descargado últimamente.» | no ha actuado (1/3) |
| ¿tengo algún PDF en el escritorio? | llm | «Veamos si hay alguno en el escritorio.» | no ha actuado |
| no encuentro el Excel del presupuesto | llm | «echa un vistazo a tu escritorio y a las carpetas de Trabajo y Documentos. Si no está allí, busca por el PC.» | no ha actuado |
| ¿tengo algún archivo que se llame curriculum? | llm | «Veamos si tienes un archivo llamado curriculum en alguna carpeta.» | no ha actuado (1/3) |
| ábreme el último documento que descargué | no_encontrado | No encuentro «el ultimo documento que descargue» | no ha actuado |
| lleva los PDF de Descargas a Documentos | llm | move_files({"folder": "Descargas", "kind": "documents", "destination": "Documentos", "names": []}) | extension=None (esperaba 'pdf') |
| pasa las capturas del escritorio a Imágenes | llm | move_files({"destination": "Imágenes", "names": ["Escritorio"]}) | llamada no válida (move_files: Field required; en Nyx se reintentaría) |
| duplica en el escritorio el documento más reciente de Descargas | llm | open_path({"target": "Descargas"}); list_files({"folder": "Descargas", "newest": 1}); open_path({"target": "Escritorio"} | esperaba copy_files |
| cámbiale el nombre a la carpeta Nueva carpeta del escritorio por Trabajo | llm | «» | no ha actuado |
| ya no quiero las capturas del escritorio, quítalas | llm | «Desactivando la opción de capturas del escritorio.» | no ha actuado |
| limpia Descargas de archivos comprimidos | llm | find_files({"folder": "Descargas", "kind": "archives"}); delete_files({"folder": "Descargas", "kind": "archives"}) | llamada no válida (find_files: Value error, falta query (parte del nombre) o extension; en Nyx se reintentaría) |
| mañana tengo que levantarme a las seis y media | llm | «Pon una alarma para las 6:30 para que te despiertes a tiempo.» | no ha actuado |
| quiero que me despiertes a las 9 los fines de semana | llm | «Poné una alarma para los fines de semana a las 9. ¿Querés que sea cada viernes y sábado?» | no ha actuado |
| a las 5 de la tarde tengo médico, avísame | llm | «[setalarm {"time": "13:00", "label": "medicina"}]» | no ha actuado (1/3) |
| la pasta tarda 12 minutos, avísame cuando esté | llm | set_alarm({"time": "13:56", "label": "pasta lista"}) | esperaba set_timer |
| en un cuarto de hora tengo que salir, avísame | llm | «Pon una alarma para las 01:59.» | no ha actuado |
| ya no hace falta que me despiertes mañana | llm | «no alarma» | no ha actuado (1/3) |
| ¿cómo te llamo sin decir tu nombre? | llm | «llámame Nyx» | no ha actuado |
| ¿guardas lo que te digo? | llm | «Ni guardo ni recuerdo nada, confidencialidad» | no ha actuado |
| ¿qué haces cuando estoy jugando? | llm | «Estoy aquí para ayudarte. Cuando estás jugando, solo activo el modo partida, que significa que solo responderé por voz  | no ha actuado |
| cuando te escriba no me contestes hablando | llm | «No hablo» | no ha actuado |
| no te actives tan fácilmente | llm | «relajado, no te preocupes» | no ha actuado |
| mientras juego no pienses, solo obedece órdenes | llm | «Entendido. Mientras juegas, solo obedezco órdenes sin pensar. ¿En qué puedo ayudarte?» | no ha actuado |
| léeme lo que copié antes | llm | «En voz alta te leeré lo que tienes copiado.» | no ha actuado (1/3) |
| pásame al inglés el texto que he copiado | llm | «En inglés, el texto que has copiado es: the text you copied.» | no ha actuado |
| redáctame en Word: Querido Juan | llm | «redacción, escribe en Word» | no ha actuado |
| me he equivocado, déjalo como estaba | llm | «Entendido. No haré cambios hasta que me indiques lo que deseas hacer. ¿Necesitas algo en particular ahora?» | no ha actuado |
| crea una carpeta Recibos en Documentos y mueve ahí los PDF de Descargas | llm | create_folder({"parent": "Documentos", "name": "Recibos"}); move_files({"folder": "Descargas", "kind": "pdf", "newest":  | llamada no válida (move_files: Input should be 'images', 'videos', 'documents', 'audio', 'archives', 'installers' or 'folders'; en Nyx se reintentaría) |
| apaga el wifi y bloquea el ordenador | llm | system_power({"action": "shutdown", "enabled": false}) | llamada no válida (system_power: Extra inputs are not permitted; en Nyx se reintentaría) |
| ¿hará calor el sábado? | llm | «Para saber la temperatura, necesito saber a qué ciudad te refieres. ¿En qué ciudad quieres saber si hará calor el sábad | no ha actuado |

## Notas (6.25, quinta tanda: ajustes, internet, zoom y los fallos del router de la 6.17)

Con semilla (1), frente a la tanda 4 (329/377): **343/385**. **Router 231/231**: ya no falla
ninguna frase que resuelva el router.

- Reglas nuevas: `settings_need` («quiero cambiar el fondo de pantalla», «¿cómo cambio el
  idioma?», «no me va el micrófono, llévame a donde se configura»; solo páginas de
  Configuración con ese nombre exacto), `nyx_change` («quiero cambiarte la voz», «quiero cambiar
  tu color»; con «te» o «tu», no «la voz del vídeo»), `city_live` («vivo en Sevilla»; no «vivo
  en un piso»), `internet_off` («quítame internet un rato»), `zoom` («acerca la página, que no
  veo la letra») y `find_in_page` («busca en esta página la palabra precio» → Ctrl+F y escribe
  la palabra; en la batería pasa de esperar una acción a esperar ese plan de dos pasos).
- Los 3 fallos del router de la 6.17, arreglados: «cierra el dis cord» (nombre mal oído →
  Discord, compartido con las ventanas en `comun._fix_typo`), «pon la música en aleatorio»
  (tanda 4) y «busca en esta página…» (antes buscaba archivos).
- 8 frases nuevas sin probar contra las reglas: todas bien.
- Fallan ahora y no en la tanda 4: 4 frases, todas por el LLM (variación).
