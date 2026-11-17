# Plan de la versión 0.8 — Organización y seguridad

> **Aprobado por el usuario el 2026-11-16 («la 0.8 ahora»), menos la 8.13: las formas de Nyx
> serán una extensión (seguramente de pago), más adelante.** Borrador de Claude del 2026-11-15. El usuario
> pidió hacer la 0.8 antes de la beta y seguir sin parar apuntando las dudas
> (`REVISAR.md` 24); mientras no lo apruebe, se empieza por lo que no cambia nada visible ni
> el modo partida (bloque B, núcleo), y lo que lleva interfaz se hace como prototipo.
> Fuente: [HOJA-DE-RUTA.md](HOJA-DE-RUTA.md) §2 (0.8) y §5 (modos), y lo que pasa de la 0.7
> (`PLAN-0.7.md`, 7.09 y 7.10). Funciona como los planes anteriores: una tarea por sesión, sus
> comprobaciones (§0.3 de `PLAN-0.6.md`), un commit y su fila en el Registro.

**Objetivo de la 0.8:** que Nyx ayude a organizarse (notas, listas, tareas, calendario,
dictado, resúmenes, documentos recientes) y a proteger la privacidad (modos, bloquear, quién
usa el micro y la cámara), sin tocar el rendimiento en partida.

**Para cerrar la 0.8** (HOJA-DE-RUTA §2): cada función con sus frases en la batería y sus
pruebas; la batería no baja (388/409 con `nyx-r2:7b` en la 7.17) y el coste en partida sigue
dentro del objetivo (SPEC §14).

---

## 0. Reglas propias de la 0.8

- **Todo local.** Notas, listas, tareas y calendario en una base SQLite en
  `%LOCALAPPDATA%\Nyx` (copia en la de seguridad de las actualizaciones, 9.05). Nada sale del
  PC; importar un `.ics` es leer un archivo que elige el usuario.
- **Borrar es a la papelera o con deshacer.** Una nota, lista o tarea borrada se puede
  recuperar (deshacer 30 s y «papelera» propia de 30 días); nunca borrado permanente.
- **Lo privado no se enseña sin querer:** en el modo Privacidad, las burbujas no llevan
  contenido (ni notas, ni citas, ni lo que se dicta).
- **El modo partida no cambia** al pasar a ser un modo: mismas políticas, mismos tiempos, y se
  comprueba jugando antes de cerrar.

## 1. Orden y dependencias

```text
A. Organización        8.01 → 8.02 → 8.03 · 8.04 · 8.05 · 8.06    (núcleo primero)
B. Seguridad básica    8.07 · 8.08                                (independientes)
C. Modos               8.09 (diseño) → 8.10 → 8.11                (lo que pasa de la 0.7)
D. Interfaz            8.12 (prototipo antes) · 8.13 (formas, de la 7.09)
E. Cierre              8.14
```

## 2. Bloque A — Organización

### 8.01 Notas, listas y tareas (núcleo) · Claude

`nyx/organizer/` con una base SQLite (`organizer.db`): notas rápidas (texto y fecha), listas
con elementos (la compra, pendientes) y tareas con fecha opcional que avisan como un
recordatorio (`alarms`). Herramientas `note` (apuntar, leer, buscar), `list_items` (añadir,
quitar, leer, vaciar con deshacer) y `task` (crear, completar, ver las de hoy). Reglas del
router para lo seguro («apunta que…», «añade leche a la lista de la compra», «¿qué tengo en la
lista?»), con variantes de respuesta por tono. `save_note` (la nota en el Bloc de notas) sigue
igual: «apunta en una nota» abre el Bloc; «apunta que…» guarda en Nyx. **A decidir:** si las
notas rápidas también se guardan como archivo en `Documentos\Notas de Nyx` (para verlas fuera
de Nyx) o solo en la base.

### 8.02 Calendario local · Claude

Citas con fecha, hora, duración y aviso (el planificador de alarmas), «¿qué tengo mañana?»,
«mueve la cita del dentista al jueves», importar un `.ics` (biblioteca `icalendar`, BSD: se
comprueba la licencia antes). Repeticiones sencillas (cada semana, cada mes). Sin cuentas
(Outlook y Google: 1.3).

### 8.03 Recordatorios por contexto · Claude

«Cuando abra Discord, recuérdame…», «cuando llegue a casa» no (sin ubicación continua). Usa
el aviso de app en primer plano que ya tiene el modo partida (`game/` detecta procesos); el
recordatorio salta una vez y se borra (con deshacer). Nunca en partida: espera a que acabe.

### 8.04 Dictado · cualquiera

«Escribe lo que te diga»: Nyx escucha seguido (como en el primer arranque) y escribe en la app
activa con `type_text` (sin Intro ni tabulador sin confirmar, como ya hace), hasta «ya está»
o un silencio largo. Puntuación hablada («coma», «punto», «nueva línea»). Nunca en juegos ni
en terminales sin confirmar.

### 8.05 Resúmenes del texto seleccionado y de documentos · Claude

El del portapapeles ya existe (`clipboard`). Añadir: el texto seleccionado (copiarlo con
Ctrl+C y devolver el portapapeles como estaba, nunca en juegos) y un documento («resume el
PDF de Descargas»: `pypdf` BSD para PDF, `python-docx` MIT para Word, texto plano), que llega
al modelo como información de fuera (como una web), por trozos si es largo.

### 8.06 Documentos recientes · cualquiera

«Abre el último Word», «¿qué documento estaba editando ayer?»: la carpeta Recientes de Windows
(accesos directos `.lnk`) y, si hace falta, las listas de saltos. Sin indexar nada nuevo.

## 3. Bloque B — Seguridad básica

### 8.07 Quién usa el micrófono y la cámara · Claude

«¿Quién está usando el micro?», «¿qué apps han usado la cámara hoy?»: el registro de
privacidad de Windows (`CapabilityAccessManager\ConsentStore\{microphone,webcam}`, por usuario,
con `LastUsedTimeStart/Stop`; en uso si `Stop` es 0). Solo lectura. Nyx se nombra a sí misma
si es ella. Aviso opcional (apagado por defecto) cuando una app empieza a usar la cámara.

### 8.08 Bloquear y ocultar · cualquiera

Bloquear el PC por voz ya existe (`system_power`, verde): frases en la batería y la regla del
router (hoy «apaga el wifi y bloquea» acaba en apagar, con confirmación). Ocultar apps
concretas: minimizarlas y quitarlas de la barra mientras dure (las devuelve al salir del modo
Privacidad o con «enséñalas»), nunca juegos ni Nyx.

## 4. Bloque C — Modos (de la 0.7)

### 8.09 Sistema de modos: diseño · Claude · DECISIÓN

Con HOJA-DE-RUTA §5: disparadores (voz, automáticos, bandeja), acciones al entrar y al salir
que se deshacen, comportamiento de Nyx (voz, burbujas, monitor, tono) y políticas de
herramientas por modo. **La partida pasa a ser el primer modo sin cambiar cómo funciona.**
Propuesta escrita y el visto bueno del usuario antes de tocar `game/` y `gamemode/`.

### 8.10 Modos Trabajo, Noche y Privacidad · Claude

Trabajo (abre y coloca las apps elegidas, silencia lo que distrae, voz baja), Noche (volumen
bajo, voz más suave, sin sonidos, y abre luz nocturna y no molestar en Configuración: decisión
de la 7.10) y Privacidad (micrófono de Nyx solo con atajo, burbujas sin contenido, sin
búsquedas en internet, oculta las apps elegidas: 8.08). Se prueba jugando que Partida sigue
igual.

### 8.11 Modos como extensiones · Claude

El tipo `mode` del manifiesto (hoy se acepta y no se usa): un modo de fuera solo puede usar
acciones y ajustes que un preajuste ya puede tocar, nunca políticas de seguridad. Tercer
ejemplo de la guía de extensiones (el que faltaba de la 7.13).

## 5. Bloque D — Interfaz

### 8.12 Organización en la interfaz · cualquiera (prototipo antes)

Prototipo HTML (como en la 6.28) y visto bueno del usuario: panel de notas, listas y tareas
junto a Nyx («enséñame la lista de la compra»), la agenda del día, Ajustes → Modos y el aviso
de cámara. SPEC §12 al pie de la letra.

### 8.13 Formas de extensión en Nyx (de la 7.09) · **fuera de la 0.8** (decisión 2026-11-16)

Dibujar en la isla la forma de una extensión con el preámbulo del contrato
(`docs/extensiones/formas.md`), volver a la de siempre si no compila o cuesta demasiado, y
registrar la forma actual como `tepnyx.forma-nyx` (la predeterminada). Elegirla en Ajustes →
Apariencia. Se mide el coste en partida.

## 6. Bloque E — Cierre

### 8.14 Cierre de la 0.8 · Claude

Revisión, batería con las frases nuevas, coste en partida, SPEC (organización, seguridad y
modos), `CHANGELOG.md` y `CLAUDE.md` (siguiente: 0.9, la beta).

## 7. Fuera de la 0.8

- Calendarios de Outlook y Google: 1.3.
- Modos Streaming y Relax: 1.1.
- Programas desconocidos y apps que se inician con Windows: 1.3.

## 8. Registro

| Tarea | Agente | Commit | Notas para la revisión | Revisado |
| --- | --- | --- | --- | --- |
| 8.01 | Claude | (este commit) | **Listas y tareas** (las notas ya eran archivos con `save_note`: «apúntame que…» sigue igual). `nyx/organizer/store.py`: SQLite en `%LOCALAPPDATA%\Nyx\organizer.db`; quitar, vaciar o borrar solo marca (`deleted`) y se deshace; listas por nombre como lo dice la gente (`list_key`: «la lista de la compra» = «compra»), sin repetidos, artículos fuera. Herramientas verdes con deshacer: `list_items` (añadir, quitar, leer, tachar, vaciar, ver listas; sin decir la lista busca en la que esté) y `task` (con día y hora opcionales: con hora avisa por las alarmas de Nyx; hecha o borrada quita el aviso y deshacer lo devuelve). Router (`router/listas.py`, antes de las reglas de archivos): añadir, leer, quitar, tachar, vaciar, listas, tarea sin fecha y «¿qué tareas tengo hoy?»; nunca listas de música ni lo que lleva fecha (al modelo). **Grupos a demanda** (`Group.lazy`): las 47 herramientas de la 0.7 llenaban justo el presupuesto con 12.288 de contexto (27.033 caracteres), así que las nuevas solo se añaden **al final** cuando la frase habla de su tema; en las frases de siempre el modelo ve exactamente lo mismo. Batería: 10 frases nuevas, 10/10 (primer token ~0,67 s en las que añaden el grupo). pytest 1.946. | |
| 8.07 | Claude | (este commit) | **Quién usa el micrófono y la cámara.** `nyx/winapi/privacy.py` lee (solo lectura) el registro de privacidad de Windows por usuario (`CapabilityAccessManager\ConsentStore\{microphone,webcam}`: apps de la Tienda y `NonPackaged` con su ruta; FILETIME en UTC a la hora del PC; en uso si no tiene `Stop`), con el nombre del programa por su descripción de versión, una vez por nombre (varias versiones del mismo, la más relevante) y Nyx como «yo» (solo su Python, su app o el de extensiones; la grabadora no). Herramienta `privacy_check` (verde, en partida también; grupo a demanda «privacidad»): ahora, hoy o esta semana, micrófono, cámara o los dos. Router: «¿quién está usando el micro?», «¿alguien me está escuchando?», «¿qué apps han usado la cámara hoy?». Probado en este PC de verdad (Discord usando el micrófono). Batería: 4 frases nuevas, 4/4. El aviso opcional cuando una app empieza a usar la cámara queda para la interfaz (8.12). pytest 1.955. | |
| 8.06 | Claude | (este commit) | **Documentos recientes.** `nyx/winapi/recent.py`: los accesos directos de la carpeta Recientes de Windows (`%APPDATA%\Microsoft\Windows\Recent`), resueltos con `WScript.Shell` en su hilo (COM iniciado y cerrado), del último abierto al más antiguo (la fecha del acceso directo), sin repetidos, solo los que aún existen y nunca carpetas ni programas; por tipo (Word, Excel, PowerPoint, PDF, imagen, vídeo, texto). Herramienta `recent_files` (verde; abrir, al terminar la partida como `open_path`; grupo a demanda «recientes»): abrir el último o decir cuáles. Router antes de las reglas de archivos: «abre el último Word», «ábreme otra vez el Excel que estaba usando antes», «¿qué documentos he abierto hoy?», «¿cuál fue el último Excel que abrí?», «¿cómo se llamaba el PDF que abrí ayer?»; «el último archivo de Descargas» sigue siendo de archivos. Probado con la carpeta de verdad y con accesos directos creados en una carpeta temporal. Batería: 4 frases nuevas, 4/4 (dos pasaron al router tras fallar en el modelo). | |
| 8.02 | Claude | (este commit) | **Calendario local.** Citas en `organizer.db` (`events`; borrar solo marca), con día, hora (sin hora, todo el día), duración y aviso (15 min antes por defecto; las de todo el día, a las 9), y repeticiones sencillas: cada semana, mes (el mismo día; si el mes no lo tiene, ese mes no) o año. `nyx/organizer/calendar.py`: las veces de cada cita en un intervalo y los avisos de los próximos 7 días con las alarmas de Nyx (que solo se repiten a diario), renovados cada hora y una vez por cita (`event_alarms`). Importar un `.ics` con `icalendar` (BSD-2; `python-dateutil` y `tzdata`, Apache-2.0: `LICENCIAS.md`): lo de los últimos 30 días en adelante y lo que se repite, sin repetir UID, con el aviso del archivo si trae. Herramienta `calendar` (verde, con deshacer; grupo a demanda «agenda»): apuntar, ver un día o la semana (con las tareas de ese día), mover, borrar, importar. Router (`router/agenda.py`): «¿qué tengo mañana?», «¿tengo algo el sábado por la tarde?», «tengo dentista el jueves a las 5» (de 1 a 7 sin decir más, por la tarde), «tengo clase de inglés todos los martes a las 6», «apunta en el calendario la boda de Luis el sábado», «mueve la cita del dentista al viernes», «cancela la reunión con Ana», «importa el calendario de Descargas»; lo de fechas libres va al modelo (2 de 3 bien con `nyx-r2:7b`, la tercera pasó al router). Batería: 10 frases nuevas; voz 3.212/3.212. pytest 2.088. | |
| 8.05 | Claude | (este commit) | **Resúmenes de lo seleccionado y de documentos.** Herramienta `read_text` (verde; grupo a demanda «documentos»): lo leído vuelve al modelo como contenido de fuera (`external`, como el portapapeles), que resume, traduce o contesta; `message` solo dice de dónde viene. **Selección** (`winapi/selection.py`) en la última ventana que no es Nyx: primero UI Automation (el control con patrón de texto que tiene algo seleccionado; no toca portapapeles ni teclado) y, si no, Ctrl+C solo si el portapapeles está vacío o tiene texto, que se devuelve como estaba (una imagen copiada no se pierde: entonces no se hace); nunca en juegos ni en partida, y en terminales solo UIA. **Documentos** (`nyx/textfiles.py`): PDF con `pypdf` (BSD-3), Word leyendo el XML del `.docx` sin otra dependencia, y texto; por nombre o el último de una carpeta; 6.000 caracteres por vez y, de un PDF largo, las páginas que se digan («resume las páginas 5 a 10 del informe»). Lo de dividir un documento largo en trozos y resumir cada uno queda fuera (muchas llamadas al 7B): se dice qué parte se ha leído. Router (`router/documentos.py`). Batería: 5 frases nuevas (las dos que fallaba el modelo pasaron al router); voz 3.267/3.267. pytest 2.100. **Sin probar aún con la selección de verdad** (UIA en Word, Edge, el Bloc de notas). | |
| 8.08 | Claude | (este commit) | **Bloquear y ocultar.** Bloquear: «bloquéalo», «bloquea» a secas, «me voy, bloquea» y órdenes encadenadas («apaga el wifi y bloquea» → plan de dos pasos por el router; antes acababa en el modelo). Ocultar: `hide_apps` (amarilla, con deshacer; en partida, al terminar) oculta del todo las ventanas de una app (`SW_HIDE`: ni pantalla, ni barra de tareas, ni Alt+Tab; la app sigue abierta), nunca juegos ni Nyx, y las apunta en `ocultas.json` antes de ocultarlas para devolverlas siempre: con «enséñalas» / «vuelve a mostrar Discord», al cerrar Nyx y al arrancarla (si se cayó). «Oculta Discord» a secas sigue minimizando (lo de siempre); del todo es «oculta Discord del todo / de la barra / para que no se vea». «Enséñalo» solo va a esta herramienta si hay algo oculto (si no, es lo último encontrado, del modelo). Probado con una ventana de verdad (oculta y vuelve). Batería: 3 frases nuevas. El modo Privacidad (8.10) usará esto. | |
| 8.03 | Claude | (este commit) | **Recordatorios por contexto.** El detector de partida (que ya mira la ventana activa cada 2 s) avisa al cambiar de app (`ForegroundChanged`: proceso y título, nada sale del PC). `organizer/context.py` mira los recordatorios pendientes (`app_reminders` en `organizer.db`): por el ejecutable si Nyx conoce la app y, si no, por el nombre en el proceso o el título. Salta una vez como una alarma de Nyx (sonido, voz y notificación) y queda como hecho; jugando, espera al final de la partida. Herramienta `app_reminder` (verde, con deshacer; grupo a demanda «al_abrir»): apuntar, ver, quitar. Router (`router/contexto.py`): «cuando abra Discord, recuérdame…», «la próxima vez que entre en Steam avísame de…», «recuérdame mirar el correo cuando abra Outlook»; lugares («cuando llegue a casa») no, al modelo, que explica que sin ubicación no se puede. Batería: 2 frases nuevas. pytest 2.116. | |
| 8.04 | Claude | (este commit) | **Dictado.** Herramienta `dictation` (amarilla; bloqueada en partida; grupo a demanda «dictado»): empieza en la última ventana que no es Nyx (o la app que se diga), nunca en juegos ni terminales. `nyx/dictation.py`: mientras está activo, el pipeline escucha seguido sin «Nyx» (como el primer arranque) y escribe cada frase en su ventana (`keys.write`), con un espacio entre trozos; puntuación hablada («coma», «punto», «dos puntos», «nueva línea», «punto y aparte», «abre/cierra interrogación», comillas, paréntesis…) y mayúscula tras punto; una línea nueva es Mayús+Intro, nunca Intro a secas (en un chat enviaría). Termina con «ya está» / «fin del dictado», a los 20 s sin hablar (contados desde lo último oído, aunque la primera escucha sea la ventana corta de seguimiento), al escribirle a Nyx, si empieza una partida o si la ventana ya no está. Nada de lo dictado va al router ni al cerebro. Router (`router/dictado.py`): «escribe lo que te diga», «empieza el dictado en Word», «voy a dictar», «termina el dictado». Pruebas con el pipeline de punta a punta. **Sin probar aún con el micrófono de verdad.** | |
| 8.09–8.12 | Claude | (este commit) | **Modos.** Propuesta `docs/MODOS.md` aprobada el 2026-11-17 (Partida igual por dentro; Privacidad sin red; automáticos apagados; en Noche las alarmas como siempre). `nyx/modes/manager.py`: un modo elegido a la vez; acciones al entrar de una lista cerrada (`open_app`, `window_layout`, `set_volume`, `media_control`, `hide_apps`, `open_settings`) ejecutadas con las herramientas propias de Nyx y deshechas al revés al salir, al cambiar de modo o al cerrar Nyx; pedido jugando, al acabar la partida; Noche automática por horas y Trabajo al abrir una app (`ForegroundChanged`), apagados por defecto. Cómo es Nyx: la voz con el volumen del modo (`GainPlayer`, solo la de Nyx: las alarmas usan el reproductor de siempre), Privacidad sin activación por voz (`pipeline.wake_allowed`), burbujas sin contenido en el puente salvo las confirmaciones, y sin red: el executor bloquea `web_search`, `open_url`, `get_weather`, `install_app` y `nyx_update`, la API de extensiones niega `net`/`ws`/`oauth` y los datos de uso no se envían. Herramienta `mode` (verde; grupo a demanda «modos») y router («modo trabajo», «activa el modo noche», «sal del modo», «¿en qué modo estás?»; «modo avión/oscuro/incógnito» no). **8.11:** modos de extensiones (`modes/*.json`: nombre, voz normal o baja, hasta 8 acciones de la lista cerrada; nunca activación, burbujas, red ni políticas; los de Nyx no se pueden pisar) y plantilla `nyx_ext.py new --tipo mode`. **8.12:** Ajustes → Modos (apps de Trabajo, volumen y horas de Noche, apps que oculta Privacidad, «Activar» y «Salir del modo», «· activo» en el que está). Protocolo v25 (`mode`). Hecho sin prototipo (el usuario pidió terminar el plan): sin indicador fijo junto a Nyx (obligaría a dejar una ventana visible en reposo), solo la burbuja al cambiar; ni menú de modos en la bandeja, ni panel de listas junto a Nyx, ni aviso de cámara (REVISAR 29). | |
| 8.14 | Claude | (este commit) | **Cierre de la 0.8** (2026-11-17), pendiente de que el usuario la pruebe. Batería con `nyx-r2:7b`: **436/452 (96 %)** (router 307/307, modelo 122/138, negativas 7/7; `docs/benchmarks/bateria-0.8-nyx-r2.md`), por encima de la 7.17 (388/409); batería de voz 3.377/3.377; pytest 2.139. SPEC §7 y §9.1 (modos), CHANGELOG, CLAUDE.md y REVISAR 29 al día. Sin medir el coste en partida (necesita jugar): los modos no tocan `game/` y lo nuevo solo mira la ventana activa con la lectura que ya hacía el detector. Instalador 0.9.0 recompilado con todo. | |
