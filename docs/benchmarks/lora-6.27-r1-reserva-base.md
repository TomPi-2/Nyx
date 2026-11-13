# Batería de frases · 2026-11-13 09:21

Modelo: `base`. Frases: 80. **Acierto: 50/80 (62 %)**.

Herramientas: todas (caben en su parte del contexto). Semilla del modelo: 1.

Primer token en lo que pasa por el LLM (primera pasada): mediana **5089 ms**, media **5449 ms**, peor 9185 ms.

| Camino | Frases | Acierto | Latencia mediana | Peor |
| --- | --- | --- | --- | --- |
| router | 25 | 25/25 | 0 ms | 2 ms |
| llm | 55 | 25/55 | 5089 ms | 9187 ms |

## Fallos

| Frase | Camino | Qué hizo | Por qué |
| --- | --- | --- | --- |
| oye, me abres el Spotify que quiero poner algo de fondo | llm | «openapp{"name": "Spotify"}» | no ha actuado |
| ponme el Discord, porfa | llm | «Pon el Discord.» | no ha actuado (1/3) |
| voy a jugar un rato al Fortnite, ábremelo | llm | «openapp{"name":"Fortnite"}» | no ha actuado (1/3) |
| quiero escribir una carta, ábreme el Word | llm | «openapp{"name": "Word"}» | no ha actuado |
| trae el Spotify delante | llm | «Spotify está abierto, tráelo al frente.» | no ha actuado |
| quita el Discord de la vista | llm | «cambia a Discord (name=Discord)» | no ha actuado |
| echa el Chrome a la derecha | llm | «chrome/cambia a Chrome chrome/chrome al otro monitor» | no ha actuado |
| no quiero ver más el Discord, ciérralo | llm | «closeapp(name=Discord)» | no ha actuado (1/3) |
| el Chrome está sonando muy alto | llm | «reduce el volumen de Chrome a un nivel más bajo.» | no ha actuado |
| para la canción un momento | llm | «¿Qué canción quieres saber?» | no ha actuado |
| esta no me gusta, la siguiente | llm | «no me gusta» | no ha actuado |
| dale otra vez a la música | llm | «reproduce la canción que estás escuchando» | no ha actuado |
| ¿quién canta esto que está sonando? | llm | «nowombre ¿qué suena?» | no ha actuado |
| despiértame pasado mañana a las ocho menos cuarto | llm | set_alarm({"time": "07:56", "day": "tomorrow"}) | time='07:56' (esperaba '07:45') |
| las galletas tienen que estar 15 minutos en el horno, avísame | llm | «pon la alarma para las 09:26 para recordarte.» | no ha actuado |
| ¿qué alarmas tengo puestas para mañana? | llm | «¿Cuáles alarmas tienes puestas para mañana?» | no ha actuado |
| ¿cuánto tiempo llevo con el cronómetro? | llm | «status» | no ha actuado |
| ¿el portátil se está cargando? | llm | «No puedo verificar cómo se está comportando el portátil sin consultar el nivel de batería. ¿Podrías comprobarlo por fav | no ha actuado (1/3) |
| ¿cuánta RAM estoy gastando ahora mismo? | llm | «consulta la RAM en uso.» | no ha actuado |
| ¿tengo hueco en el disco para otro juego? | llm | «consulta el espacio libre en el disco para juegos. En español, hoy es viernes 13 de noviembre de 2026 a las 09:13.» | no ha actuado |
| ¿qué programa está tirando tanto del procesador? | llm | «consulta el proceso que más consume.» | no ha actuado |
| ¿cómo va de carga el procesador? | llm | «consulta el uso de la CPU. <toolcall> <toolcall>» | no ha actuado |
| ¿qué tiempo va a hacer el fin de semana? | llm | «Para saber el tiempo del fin de semana, necesito saber a qué ciudad te refieres. ¿Podrías decírmela?» | no ha actuado |
| conéctate al wifi otra vez | llm | «Pon el wifi de nuevo.» | no ha actuado |
| enséñame lo último que me he bajado | llm | «No tengo acceso a tu historial de descargas sin conexión a internet.» | no ha actuado |
| mueve las fotos del escritorio a Imágenes | llm | «movefiles{"folder":"Escritorio", "names": [".jpg", ".png", ".jpeg"], "destination": "Imágenes"}» | no ha actuado |
| quiero cambiar el idioma del teclado | llm | «No puedo cambiar el idioma del teclado directamente, ya que esa configuración se gestiona desde los ajustes de Windows. | no ha actuado |
| ábreme la web de la Wikipedia | llm | «abre https://esxito.wiki» | no ha actuado |
| copia esto: nos vemos a las cinco | llm | «Por supuesto, copiaste: "nos vemos a las cinco".» | no ha actuado |
| habla un poco más despacio | llm | «nychcontrol{"setting": "velocidad de la voz", "value": "más despacio"}» | no ha actuado |
