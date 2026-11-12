# Batería de frases · 2026-11-12 20:38

Modelo: `qwen2.5:7b`. Frases: 337. **Acierto: 256/337 (76 %)**.

| Camino | Frases | Acierto | Latencia mediana | Peor |
| --- | --- | --- | --- | --- |
| negativa | 7 | 7/7 | 0 ms | 0 ms |
| router | 142 | 139/142 | 0 ms | 6 ms |
| llm | 185 | 110/185 | 429 ms | 2362 ms |
| no_encontrado | 3 | 0/3 | 2 ms | 2 ms |

PC de referencia (RX 7700 XT), 3 pasadas por frase del LLM (cuenta la mayoría), 39
herramientas en la lista del modelo, `num_ctx` 12.288. **Es la línea base de la 6.20** (grupos
de herramientas): lo que venga después se compara con esto.

## Qué dice (tarea 6.17, 2026-11-12)

- **La batería anterior engañaba.** Sus 31 frases del LLM estaban afinadas a mano y daban el
  100 %. Con 154 frases nuevas que el modelo no había visto, lo que llega al LLM acierta
  **110/185 (59 %)**: las nuevas, ~51 %. El router sigue casi perfecto (139/142).
- **El fallo principal (53 de 75) es no actuar:** el 7B contesta en texto en vez de llamar a
  la herramienta. Dos formas:
  - Repite la orden como texto: «pon el volumen al 50», «Pon una alarma para las seis y media
    de mañana». Pasar ese texto otra vez por el router solo rescataría 5 de 53: no es la
    solución.
  - **Se inventa el estado del PC** (va contra el objetivo de la 0.6): «La alarma de mañana
    está programada para las 7:00», «El cronómetro marca 2 horas, 36 minutos», «Mañana en
    Barcelona hará 15 grados», «La temperatura hoy es de 8 °C». Pasa sobre todo con las
    preguntas: el prompt dice que las preguntas se contestan en texto, y la regla de no
    afirmar el estado del PC sin herramienta no basta.
- **9 llamadas no válidas** (parámetros que no existen: `focus_window` con `action`,
  `system_power` con `enabled`, `move_files` sin `destination`); en Nyx se reintentarían una
  vez con el error.
- **9 con otra herramienta:** «pon el Chrome en grande» → cambiar el tamaño de Nyx; «quita
  de en medio esta ventana» → cerrar; «entra en mi correo de Gmail» → abrir app; «ya no
  quiero las capturas del escritorio» → Configuración.
- **6 fallos del router** apuntados en `docs/ERRORES.md` (frases largas tras el nombre que no
  pasan al LLM, «cierra el dis cord», «pon la música en aleatorio», «busca en esta página…»).

## Qué hacer con esto

1. **6.20b mide contra esta línea base.** Hipótesis a comprobar: con 7 fijas + un grupo
   pequeño, el modelo duda menos y actúa más. Un cambio cada vez, para saber qué ayuda.
2. Después, lo que quede de «no actúa», sobre todo las preguntas de estado: el selector ya
   sabrá qué grupo es (tiempo, alarmas, estado del equipo), así que puede avisar al modelo
   de que esa pregunta se contesta consultando, sin tocar el prompt de sistema (no rompe la
   caché).
3. Los 6 del router, en la próxima tanda de `ERRORES.md`.

## Fallos
| Frase | Camino | Qué hizo | Por qué |
| --- | --- | --- | --- |
| necesito la calculadora | llm | «Aún no sé hacer eso.» | no ha actuado |
| arranca el Discord que voy a hablar con los colegas | no_encontrado | No encuentro «el discord que voy a hablar con los colegas» | no ha actuado |
| vamos a echar una partida al Fortnite | llm | open_settings({"page": "partida"}) | esperaba open_app (1/3) |
| tengo que hacer una hoja de cálculo | llm | «Aún no sé hacer eso.» | no ha actuado |
| quiero grabar la pantalla con el OBS | llm | «Aún no sé cómo hacer eso.» | no ha actuado |
| cierra el dis cord | router | close_app({"name": "dis cord"}) | name='dis cord' (esperaba 'Discord') |
| pon el Chrome en grande | llm | nyx_control({"setting": "tamaño", "value": "más grande"}) | esperaba window_layout |
| quita de en medio esta ventana | llm | close_app({"name": null}) | esperaba window_layout |
| minimisa el crome | llm | focus_window({"action": "minimize", "name": "Chrome"}) | llamada no válida (focus_window: Extra inputs are not permitted; en Nyx se reintentaría) |
| entra en mi correo de Gmail | llm | open_app({"name": "Gmail"}) | esperaba open_url |
| quiero cambiar el fondo de pantalla | llm | «configura el fondo de pantalla, ajustes de pantalla» | no ha actuado |
| no me va el micrófono, llévame a donde se configura | llm | «Ve a los ajustes del micrófono para ver si está desactivado o si hay problemas con el dispositivo.» | no ha actuado |
| abre lo del bluetooth para emparejar unos cascos | no_encontrado | No encuentro «lo del bluetooth para emparejar unos cascos» | no ha actuado |
| quiero cambiarte la voz | llm | nyx_control({"setting": "voz al escribir", "value": "más suave"}) | esperaba open_nyx_settings |
| ¿dónde veo los atajos que has aprendido? | llm | «En los ajustes de Nyx puedes ver y cambiar mis atajos de voz.» | no ha actuado |
| ¿qué te había pedido para cuando acabe de jugar? | llm | «¿Has puesto un recordatorio para cuando acabe de jugar? Si no, ¿en qué te puedo ayudar ahora?» | no ha actuado |
| ábreme lo de Pruebas Nyx | llm | open_app({"name": "Pruebas Nyx"}) | esperaba open_path |
| no oigo nada, sube eso | llm | «pon el volumen al 50» | no ha actuado |
| está muy alto el sonido | llm | «baja el volumen un poco» | no ha actuado |
| el Discord se oye demasiado fuerte | llm | «pon el volumen de Discord al 50» | no ha actuado |
| sube el bolumen | llm | «pon el volumen un poco más alto» | no ha actuado (1/3) |
| me deslumbra la pantalla | llm | «pon el brillo al mínimo» | no ha actuado |
| no veo nada, la pantalla está muy oscura | llm | «ilumina, aumenta el brillo» | no ha actuado |
| vuelve a poner la canción de antes | llm | «reproduce de nuevo la última canción que estabas escuchando» | no ha actuado |
| pon algo para relajarme | llm | «relaja música suave» | no ha actuado |
| salta este vídeo de YouTube | llm | media_control({"action": "pause", "source": "youtube"}) | action='pause' (esperaba 'next') |
| ¿cómo se llama lo que estoy escuchando? | llm | «lo que estás escuchando.» | no ha actuado |
| ¿de quién es este tema? | llm | «Lo siento, no puedo ver el tema musical actual sin escucharlo. ¿Podrías decirme de quién es si lo recuerdas?» | no ha actuado |
| ¿qué grupo es este? | llm | «Este es un grupo de asistentes virtuales o un chat entre usuarios.» | no ha actuado |
| ¿tengo algo en el escritorio? | llm | «¿Tienes algo en el escritorio?» | no ha actuado |
| ¿qué fotos hay en Imágenes? | llm | find_files({"newest": 5, "folder": "Imágenes"}) | llamada no válida (find_files: Input should be a valid boolean, unable to interpret input; en Nyx se reintentaría) (1/3) |
| dime qué he descargado últimamente | llm | «Veamos lo que has descargado últimamente.» | no ha actuado (1/3) |
| ¿tengo algún PDF en el escritorio? | llm | «Veamos si hay algún PDF en el escritorio.» | no ha actuado |
| no encuentro el Excel del presupuesto | llm | «¿Has probado en la carpeta Trabajo o en Descargas?» | no ha actuado |
| ¿tengo algún archivo que se llame curriculum? | llm | «Veamos si tienes algún archivo llamado Curriculum en las carpetas habituales.» | no ha actuado |
| ábreme el último documento que descargué | no_encontrado | No encuentro «el ultimo documento que descargue» | no ha actuado |
| lleva los PDF de Descargas a Documentos | llm | move_files({"folder": "Descargas", "kind": "documents", "names": ["*.pdf"]}) | llamada no válida (move_files: Field required; en Nyx se reintentaría) |
| pasa las capturas del escritorio a Imágenes | llm | move_files({"destination": "Imágenes", "names": ["Escritorio"]}) | llamada no válida (move_files: Field required; en Nyx se reintentaría) |
| duplica en el escritorio el documento más reciente de Descargas | llm | open_path({"target": "Descargas"}); list_files({"newest": 1, "folder": "Descargas"}); open_path({"target": "Escritorio"} | esperaba copy_files (1/3) |
| cámbiale el nombre a la carpeta Nueva carpeta del escritorio por Trabajo | llm | «» | no ha actuado |
| ya no quiero las capturas del escritorio, quítalas | llm | open_settings({"page": "capturas"}) | esperaba delete_files |
| limpia Descargas de archivos comprimidos | llm | find_files({"kind": "archives", "folder": "Descargas"}) | llamada no válida (find_files: Value error, falta query (parte del nombre) o extension; en Nyx se reintentaría) |
| mañana tengo que levantarme a las seis y media | llm | «Pon una alarma para las seis y media de mañana.» | no ha actuado |
| quiero que me despiertes a las 9 los fines de semana | llm | «Pon una alarma para los fines de semana a las 9.» | no ha actuado |
| la pasta tarda 12 minutos, avísame cuando esté | llm | «Pon una alarma para 20:48, que es cuando la pasta estará lista.» | no ha actuado |
| en un cuarto de hora tengo que salir, avísame | llm | «Pon una alarma para las 20:45.» | no ha actuado |
| ¿a qué hora sonaba la alarma de mañana? | llm | «La alarma de mañana está programada para las 7:00.» | no ha actuado |
| ¿cuánto falta para que suene el temporizador? | llm | «Si no hay temporizadores, no habrá ninguno suelto.» | no ha actuado |
| ¿tengo algo programado? | llm | pending({"action": "list"}) | esperaba list_alarms |
| ¿me puedes decir cuánto falta para mi alarma? | llm | «Para saber cuánto falta, necesito que me indiques la hora exacta de tu alarma. ¿A qué hora está programada?» | no ha actuado |
| ya no hace falta que me despiertes mañana | llm | cancel_alarm({"time": "07:00"}) | llamada no válida (cancel_alarm: Extra inputs are not permitted; en Nyx se reintentaría) |
| ¿cuánto marca el crono? | llm | «El cronómetro marca 2 horas, 36 minutos.» | no ha actuado |
| ¿cómo te llamo sin decir tu nombre? | llm | «simplemente / sin nombre específico Sin nombre específico.» | no ha actuado |
| ¿guardas lo que te digo? | llm | «Aún no sé grabar conversaciones.» | no ha actuado |
| ¿qué haces cuando estoy jugando? | llm | «Cuando juegas, solo respondo por voz y no muestro nada en pantalla.» | no ha actuado |
| cuando te escriba no me contestes hablando | llm | «Entendido. Ahora estaré en modo texto. Si necesitas hablar, avísame.» | no ha actuado |
| no te actives tan fácilmente | llm | «Entendido. Esperaré tu próxima petición.» | no ha actuado |
| vivo en Sevilla | llm | «La información meteorológica se mostrará para Sevilla. ¿Necesitas saber algo en particular?» | no ha actuado |
| mientras juego no pienses, solo obedece órdenes | llm | «Entendido. Mientras juegas, solo obedezco órdenes sin pensar. ¿En qué puedo ayudarte?» | no ha actuado |
| ¿tengo que coger chaqueta para salir? | llm | «La temperatura hoy es de 8°C, te recomendaría coger chaqueta para salir.» | no ha actuado |
| ¿qué tal día va a hacer mañana? | llm | «Mañana, 13 de noviembre de 2026, no va a llover en Madrid. La temperatura máxima será de 16 grados y la mínima, 7 grado | no ha actuado |
| ¿hará bueno este finde en Valencia? | llm | «En Valencia este fin de semana podría hacer bueno, pero verifica las predicciones específicas para saber la temperatura | no ha actuado |
| ¿está nublado ahora? | llm | «todaví­a no puedo decir si está nublado, pero te lo puedo decir mañana.» | no ha actuado |
| ¿cuántos grados va a hacer mañana en Barcelona? | llm | «Mañana en Barcelona hará 15 grados.» | no ha actuado |
| tengo frío, ¿qué temperatura hace fuera? | llm | «¿Qué ciudad te interesa?» | no ha actuado |
| ¿el ordenador va muy cargado? | llm | «- Primera línea, entre corchetes: el dato clave (1 a 5 palabras) y una línea de contexto en minúsculas, separados por « | no ha actuado |
| ¿me queda sitio para instalar un juego de 100 gigas? | llm | «echa un vistazo a tu disco.» | no ha actuado |
| ¿por qué va tan lento el PC? | llm | «[consultar sistema / ¿cuánto disco libre queda?]» | no ha actuado |
| ¿tengo el portátil enchufado? | llm | «echa un vistazo a laConfiguración de Windows/ajustes de energía para saber si el portátil está enchufado.» | no ha actuado |
| ¿cuánta memoria me queda libre? | llm | system_info({"what": "disk"}) | what='disk' (esperaba 'ram') |
| ¿cuál de mis programas está gastando más memoria? | llm | system_info({"what": "ram"}) | what='ram' (esperaba 'top') |
| quítame internet un rato | llm | «Aún no sé hacer eso.» | no ha actuado |
| pásame al inglés el texto que he copiado | llm | «En inglés se dice text.» | no ha actuado |
| redáctame en Word: Querido Juan | llm | «redacción, escribe en Word» | no ha actuado |
| ábreme una pestaña de incógnito en Chrome | llm | app_action({"action": "new_incognito_window", "app": "Chrome"}) | llamada no válida (app_action: Value error, acción desconocida; usa una de: answer_call, back, bookmark, close_tab, command_palette, downloads, find, forward, fullscreen, history, incognito, like, mark_read, new_tab, new_window, next_tab, previous_tab, print, quick_open, quick_switcher, reload, reopen_tab, repeat, save, save_as, search, shuffle, toggle_deafen, toggle_mute, toggle_sidebar, up, volume_down, volume_up, zoom_in, zoom_out, zoom_reset; en Nyx se reintentaría) (1/3) |
| pon la música en aleatorio | router | media_control({"action": "play", "source": "aleatorio"}) | esperaba app_action |
| busca en esta página la palabra precio | router | find_files({"query": "en esta pagina la palabra precio"}) | esperaba app_action/send_hotkey |
| acerca la página, que no veo la letra | llm | «Pon la página al máximo para leer mejor.» | no ha actuado (1/3) |
| me he equivocado, déjalo como estaba | llm | «Vamos a deshacer la última acción que hiciste.» | no ha actuado |
| crea una carpeta Recibos en Documentos y mueve ahí los PDF de Descargas | llm | create_folder({"name": "Recibos", "parent": "Documentos"}); find_files({"folder": "Descargas", "kind": "documents", "ext | llamada no válida (move_files: Field required; en Nyx se reintentaría) |
| apaga el wifi y bloquea el ordenador | llm | system_power({"action": "shutdown", "enabled": false}) | llamada no válida (system_power: Extra inputs are not permitted; en Nyx se reintentaría) |
