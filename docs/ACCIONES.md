# Catálogo de acciones de Nyx

Todo lo que un usuario podría querer pedirle a Nyx, agrupado por áreas. La lista no se acaba nunca: sirve para priorizar, para la batería de frases (fase 6) y para ver qué falta. Se amplía con las sugerencias de los usuarios (Ajustes → Sugerencias, ver SPEC sección 13).

**Estado:** **Hecho** (funciona ya) · **3c** (en curso) · **F4, F5, F6** (fase prevista) · **Idea** (sin fase aún).
**Riesgo** (SPEC sección 8): verde se hace sin preguntar; amarillo se hace y ofrece deshacer; rojo pide confirmación.

## Reglas que no cambian

- **Nada dentro de los juegos.** Nyx puede abrir un juego, ajustar el volumen del sistema o la música mientras juegas y responder preguntas, pero **nunca** pulsa teclas, escribe, mueve el ratón ni lee la pantalla dentro de un juego. Las herramientas de teclado se niegan si la ventana es un juego (`winapi/games.py`).
- **Nunca borrado permanente.** Todo va a la papelera y se puede deshacer. «Vaciar la papelera» o Mayús+Supr no existen en Nyx.
- **Nada de dinero ni contraseñas.** Ni compras, ni pagos, ni rellenar contraseñas, ni cambiar cuentas.
- **Mensajes a otras personas, siempre confirmados** (rojo): Nyx enseña el texto y el destinatario antes de enviar.
- **Lo que sale a internet se dice** (burbuja con la fuente) y se puede desactivar.

## 1. Apps y ventanas

| Acción | Ejemplos | Estado | Riesgo |
| --- | --- | --- | --- |
| Abrir apps, juegos, webs, carpetas y páginas de Configuración | «abre Spotify», «abre el lol», «abre marca.com» | Hecho | Verde |
| Abrir en segundo plano | «abre Discord en segundo plano» | Hecho | Verde |
| Cerrar una app (pregunta si hay cambios sin guardar) | «cierra el bloc de notas» | Hecho | Amarillo |
| Traer una ventana al frente | «ve a Chrome», «enséñame Discord» | Hecho | Verde |
| Maximizar, minimizar, media pantalla, otro monitor | «pon Chrome a la izquierda», «manda esto al otro monitor» | Hecho | Verde |
| Colocar varias ventanas a la vez | «Chrome a la izquierda y Discord a la derecha» | Hecho | Verde |
| Minimizar todo / ver el escritorio | «enséñame el escritorio» | F6 | Verde |
| Cerrar todas las ventanas de una app | «cierra todas las ventanas de Chrome» | F6 | Amarillo |
| Restaurar lo que se cerró | «vuelve a abrir lo que cerré» | Hecho (deshacer 30 s) | Verde |
| Ventana siempre encima | «deja la calculadora siempre encima» | Idea | Verde |
| Escritorios virtuales | «pásate al escritorio 2», «crea un escritorio» | F6 | Verde |
| Distribuciones guardadas | «modo trabajo» (abre y coloca VS Code, Chrome y Spotify) | F6 | Verde |
| Pulsar un botón, marcar una casilla o leer un texto por su nombre | «pulsa Aceptar», «marca Recordarme», «¿qué pone en el aviso?» | Hecho (`ui_action`, UI Automation; nunca en juegos) | Amarillo (rojo si es eliminar, enviar, pagar…) |
| Instalar y desinstalar programas | «instálame el VLC», «desinstala el Zoom» | Hecho (`install_app`, con winget; enseña el nombre exacto y el editor) | Rojo |

## 2. Dentro de las apps (`app_action`, nunca en juegos)

Los atajos siguen el idioma de Windows (en español, «nuevo» es Ctrl+U y «guardar» Ctrl+G en el Bloc de notas y en Office). Las acciones «de fondo» devuelven el foco a donde estabas.

| App | Acciones | Estado |
| --- | --- | --- |
| Bloc de notas | nota nueva, cerrar nota, guardar, guardar como, buscar, imprimir, zoom | Hecho |
| Navegadores (Chrome, Edge, Opera, Brave, Vivaldi, Firefox) | pestaña nueva, cerrar, reabrir la cerrada, siguiente/anterior, ventana nueva, incógnito, atrás, adelante, recargar, historial, descargas, marcador, buscar en la página, zoom, pantalla completa | Hecho |
| Spotify | subir/bajar su volumen, aleatorio, repetir, me gusta, buscar | Hecho |
| Discord | silenciar micro, ensordecer, buscar canal o persona, buscar mensajes, contestar llamada, marcar como leído | Hecho |
| Explorador de archivos | pestaña nueva, cerrar, ventana nueva, atrás, adelante, carpeta superior, actualizar, buscar | Hecho |
| Visual Studio Code | paleta de comandos, abrir archivo, archivo nuevo, cerrar pestaña, guardar, barra lateral, buscar | Hecho |
| Word, Excel | nuevo, guardar, imprimir, buscar | Hecho |
| PowerPoint | empezar la presentación, siguiente/anterior diapositiva, salir | F6 |
| Outlook / Correo | correo nuevo, responder, buscar | F6 (enviar: rojo) |
| Teams, Zoom, Google Meet | silenciar micro, cámara, levantar la mano, colgar | F6 |
| WhatsApp y Telegram de escritorio | abrir un chat, buscar | F6 (enviar: rojo) |
| OBS Studio | empezar/parar grabación o directo, cambiar de escena (obs-websocket, sin teclas) | F6 |
| VLC y reproductores | pantalla completa, subtítulos, adelantar 10 s, velocidad | F6 |
| YouTube, Netflix, Twitch (en el navegador) | pausa, pantalla completa, subtítulos, adelantar o retroceder, saltar intro | F6 |
| Steam, Riot, Epic (lanzadores, no juegos) | abrir la biblioteca o la tienda, ver amigos, descargas | F6 |
| Calculadora | abrir y calcular («calcula 17 por 23 en la calculadora») | Idea |
| Paint, Fotos | abrir una imagen, girar, recortar | Idea |
| Ajustes propios por app | el usuario añade sus atajos («en Figma, “exportar” es Ctrl+Mayús+E») | F5 |

## 3. Música, vídeo y audio

| Acción | Ejemplos | Estado | Riesgo |
| --- | --- | --- | --- |
| Pausa, reanudar, siguiente, anterior | «pausa», «siguiente canción», «pon música» | Hecho | Verde |
| Volumen general | «sube el volumen», «volumen al 30», «silencia» | Hecho | Verde |
| Volumen de una app (mezclador) | «baja Discord al 20», «silencia Chrome» | Hecho | Verde |
| Volumen propio de Spotify | «sube el volumen de Spotify» | Hecho | Verde |
| Qué está sonando | «¿qué canción es esta?» (SMTC de Windows) | Hecho (`now_playing`) | Verde |
| Poner algo concreto | «pon Bad Bunny en Spotify», «pon lo-fi en YouTube» | F6 | Verde |
| Cambiar la salida de audio | «pon el sonido en los auriculares» | Hecho (`audio_output`: abre Sonido de Windows) | Verde |
| Cambiar el micrófono por defecto | «usa el micro Ozone» | F6 | Verde |
| Atenuar la música mientras habla Nyx | automático | F5 | — |

## 4. Archivos y carpetas

| Acción | Ejemplos | Estado | Riesgo |
| --- | --- | --- | --- |
| Crear carpeta | «crea la carpeta Fondos en Imágenes» | Hecho | Amarillo |
| Listar lo que hay | «¿qué hay en Descargas?» | Hecho | Verde |
| Buscar archivos (nombre, tipo, extensión) | «busca la factura de la luz», «los pdf de Documentos» | Hecho | Verde |
| Mover, copiar, renombrar | «mueve los 3 últimos archivos de Descargas a Documentos» | Hecho | Amarillo |
| Borrar (a la papelera, con deshacer) | «borra el último archivo de Descargas» | Hecho | Rojo |
| Recuperar de la papelera | «recupéralo» | Hecho (30 s) | Verde |
| Planes de varios pasos | «crea Fondos en Imágenes y mueve allí las fotos de Descargas» | Hecho | Según paso |
| Abrir un archivo con su programa | «abre el último pdf que descargué» | F6 | Verde |
| Ordenar Descargas por tipo | «ordena Descargas» | F6 | Amarillo |
| Comprimir y descomprimir | «comprime la carpeta Viaje», «descomprime el zip» | F6 | Amarillo |
| Archivos recientes | «¿qué estuve editando ayer?» | Idea | Verde |
| Espacio en disco | «¿cuánto espacio me queda?», «¿qué ocupa más?» | Hecho (espacio libre) / F6 | Verde |
| Convertir formatos | «pasa esta imagen a png», «une estos pdf» | Idea | Amarillo |

## 5. Tiempo, alarmas y organización

| Acción | Ejemplos | Estado | Riesgo |
| --- | --- | --- | --- |
| Alarma a una hora | «pon una alarma a las 7 y media», «despiértame mañana a las 8» | Hecho | Verde |
| Temporizador | «temporizador de 5 minutos», «avísame en media hora» | Hecho | Verde |
| Recordatorio con texto | «recuérdame a las 6 llamar a mamá» | Hecho | Verde |
| Ver y cancelar alarmas | «¿qué alarmas tengo?», «quita la alarma de las 7» | Hecho | Verde |
| Alarmas que se repiten | «todos los días laborables a las 7» | Hecho | Verde |
| Cronómetro | «empieza un cronómetro», «¿cuánto lleva?» | Hecho (`stopwatch`) | Verde |
| Notas rápidas y listas | «apunta comprar leche», «¿qué hay en la lista de la compra?» | F6 | Verde |
| Calendario | «¿qué tengo mañana?», «añade dentista el jueves a las 5» (Outlook/Google, con permiso) | Idea | Amarillo |
| Recordatorios por contexto | «cuando abra Discord, recuérdame contestar a Pablo» | Idea | Verde |

## 6. Preguntas e información

| Acción | Ejemplos | Estado |
| --- | --- | --- |
| Preguntas generales (LLM local) | «¿quién escribió el Quijote?», «¿qué es un agujero negro?» | Hecho |
| Traducciones | «¿cómo se dice hola en alemán?» | Hecho |
| Hora y fecha | «¿qué hora es?», «¿qué día cae el 25?» | Hecho |
| Cálculos y conversiones | «¿cuánto es 17 por 23?», «pasa 30 dólares a euros» (cambio: internet) | Hecho (cálculo) / F6 (divisas) |
| El tiempo | «¿va a llover mañana?» (Open-Meteo, ciudad fija en ajustes) | Hecho |
| Buscar en internet | «busca en internet quién inventó la imprenta», «busca cómo poner la barra de tareas a la izquierda» (en segundo plano: DuckDuckGo y las páginas que da, o Wikipedia, con las fuentes; o abrirlo en el navegador) | Hecho (`web_search`) |
| Actualidad | «¿quién ganó ayer el Madrid?» (noticias y resultados) | Pendiente de elegir proveedor (6.05) |
| Definiciones y sinónimos | «otra palabra para bonito» | Hecho (LLM) |
| Sobre el PC | «¿cuánta RAM uso?», «¿qué consume más CPU?», «temperatura de la gráfica» | Hecho (batería, CPU, RAM, disco, procesos) |
| Sobre la red | «¿cuál es mi IP?», «¿va bien internet?» | F6 |
| Lo que hay en pantalla | «¿qué pone aquí?», «resume esta página» (nunca en juegos) | Idea |

## 7. Escribir y portapapeles

| Acción | Ejemplos | Estado | Riesgo |
| --- | --- | --- | --- |
| Pulsar un atajo | «pulsa control s» | Hecho (`send_hotkey`) | Amarillo |
| Dictar texto en la app activa | «escribe: llego en 10 minutos» | Hecho (`type_text`) | Amarillo (rojo si lleva Intro o tabulador, o si es una terminal) |
| Trabajar con lo copiado | «traduce lo que he copiado», «resume lo copiado», «corrige la ortografía» | Hecho (`clipboard`) | Verde |
| Historial del portapapeles | «pega lo que copié antes» | Idea | Amarillo |
| Redactar | «escríbeme un correo para pedir el día libre» (en la burbuja, para copiar) | F6 | Verde |

## 8. Capturas y grabación

| Acción | Ejemplos | Estado | Riesgo |
| --- | --- | --- | --- |
| Captura de pantalla, monitor o ventana | «haz una captura», «captura de esta ventana» | Hecho | Verde |
| Captura de una región | «captura una zona» (selector) | F6 | Verde |
| Grabar pantalla | «graba la pantalla», «para la grabación» | F6 (`screen_record`) | Verde |
| Clip de lo último | «guarda los últimos 30 segundos» | Idea | Verde |

## 9. Sistema y Windows

| Acción | Ejemplos | Estado | Riesgo |
| --- | --- | --- | --- |
| Abrir cualquier página de Configuración | «abre los ajustes del bluetooth» | Hecho | Verde |
| Brillo | «baja el brillo» | Hecho (`set_brightness`) | Verde |
| Wi-Fi y Bluetooth | «apaga el bluetooth», «conecta los auriculares» | Hecho (`toggle_wifi`, `toggle_bluetooth`) | Amarillo |
| Modo noche, no molestar, modo oscuro | «activa la luz nocturna», «no molestar una hora» | F6 | Verde |
| Bloquear el equipo | «bloquea el PC» | Hecho (`system_power`) | Verde |
| Suspender, reiniciar, apagar, programar apagado | «apaga el ordenador en una hora» | Hecho (`system_power`: suspender, reiniciar, apagar) / F6 (programado) | Rojo |
| Cerrar un programa colgado | «cierra lo que se ha quedado colgado» | F6 | Rojo |
| Vaciar la papelera | — | **Nunca** (borrado permanente) | — |
| PowerShell | «¿qué IP tengo?», «¿cuánto lleva encendido el PC?» (lo que no cubre nada más) | Hecho (`run_powershell`: lista de bloqueo; las consultas de solo lectura de una lista cerrada, sin preguntar) | Rojo (verde si solo lee) |

## 10. Juegos

| Acción | Ejemplos | Estado |
| --- | --- | --- |
| Abrir un juego o su lanzador | «abre el Valorant», «abre Steam» | Hecho |
| Modo partida | Nyx se aparta, solo voz, sin robar el foco ni bajar FPS | F5 |
| Música y volumen mientras juegas | «sube la música», «siguiente canción» | Hecho |
| Preguntas sin salir del juego | «¿qué hora es?» (solo voz) | F5 |
| Lo que dejes pendiente | «abre Discord cuando acabe la partida» | F5 |
| **Dentro del juego** (teclas, chat, macros, leer la pantalla) | — | **Nunca** |

## 11. Nyx

| Acción | Ejemplos | Estado |
| --- | --- | --- |
| Deshacer | «deshaz», «recupéralo» | Hecho |
| Abrir sus Ajustes (en una sección) | «abre tus ajustes», «los ajustes de Nyx», «tu configuración del modo partida» | Hecho |
| Callar o dejar de escuchar | «calla», «no me escuches durante una hora» | F5 |
| Cambiar la voz o su volumen | «habla más bajo», «usa la voz de hombre» | F5 |
| Reiniciar Nyx | bandeja → Reiniciar núcleo; también en Ajustes | Hecho (bandeja) / F5 (Ajustes) |
| Enviar una sugerencia | Ajustes → Sugerencias, o «Nyx, sugerencia: que pueda…» | F5 |
| Atajos aprendidos | Nyx recuerda frases que ya resolvió | 3c |

## 12. Más adelante

- **Rutinas:** «buenos días» (hora, tiempo, alarmas del día y la música de siempre), «me voy» (bloquea el PC, para la música).
- **Hogar** (local, si el usuario tiene Home Assistant): luces, enchufes, termostato.
- **Accesibilidad:** leer en voz alta el texto seleccionado, lupa, alto contraste.
- **Móvil:** avisos de Nyx en el móvil, enlace del teléfono de Windows.
