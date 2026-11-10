# Changelog

Todos los cambios relevantes de Nyx. Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y versiones según [SemVer](https://semver.org/lang/es/).

## [Sin publicar]

### Añadido

- Fase 1 (en curso):
  - Núcleo: bus de eventos asyncio, protocolo versionado núcleo ↔ interfaz (pydantic), servidor WebSocket local con token y comprobación de origen, registros con rotación e ID por petición, modo `--demo`.
  - Interfaz: proyecto Tauri 2 + Svelte 5. La app Tauri es el proceso principal: lanza el núcleo con `uv`, lo reinicia si se cae (3 intentos) y le pasa el token.
  - Isla provisional: ventana sin foco, fuera de Alt+Tab y la barra de tareas, que atraviesa los clics, sigue al ratón entre monitores y se oculta del todo en reposo.
  - Prueba de cristal (menú de la bandeja; `NYX_GLASS_TEST=1` la abre al arrancar).
  - Bandeja del sistema (prueba de cristal, reiniciar núcleo, salir) e instancia única.
  - Scripts de prueba de GPU para Ollama y whisper.cpp con informe por equipo en `docs/benchmarks/`.
  - Resultados del PC de referencia (RX 7700 XT): Qwen 2.5 7B y Llama 3.1 8B al 100 % en GPU (77 y 72 tokens/s, 3/3 herramientas); whisper.cpp con Vulkan, 0,17 s por frase. LLM provisional: `qwen2.5:7b`.
  - CI en GitHub Actions (Windows): ruff, mypy, pytest, prettier, svelte-check, rustfmt y clippy.
- Fase 4 (en curso): «Nyx» de verdad.
  - 4a: `scripts/record_samples.py` (grabar positivos, palabras parecidas y uso normal) y `scripts/wake_eval.py` (aciertos por tipo y activaciones falsas por hora tras whisper).
  - 4b: modelo propio entrenado solo con datos libres (voces de Piper davefx, sharvard y LibriTTS; OpenSLR 28, 61, 71 y 72; nada de los modelos ni datos de openWakeWord, que son CC BY-NC-SA). Generación, filtro con whisper, montaje con reverberación y ruido, y entrenamiento en CPU (`core/training/`).
  - 4c: el modelo propio es el detector por defecto (`wake.engine`, `wake.sensitivity` de 1 a 10); Vosk queda como alternativa y para el «sí/no». El indicador de «escuchando» se enciende cuando whisper confirma «Nyx»: las activaciones descartadas ya no se ven. Con la voz del usuario: 88 % de aciertos (Vosk: 74 %) y 0 activaciones falsas en 30 min.
  - 4d: calibración con las muestras del usuario (`scripts/calibrate.py`, validación cruzada; solo se guarda si mejora: hoy no lo hace). Registro de activaciones en `%LOCALAPPDATA%\Nyx\activaciones` y «Nyx, eso no era para ti», que sube el umbral (+0,03, máx. +0,2). Palabras personalizadas (`wake.custom_word`, con Vosk): al menos 2 sílabas, en el vocabulario de Vosk y aviso si se parecen a palabras comunes; whisper verifica y se quitan de la frase igual que «Nyx». La verificación de voz queda para la fase 6.
- Fase 3c (cerrada; fase 3 cerrada el 2026-11-10): LLM con herramientas, alarmas y atajos aprendidos.
  - El LLM recibe las 20 herramientas en cada petición: para una acción devuelve un plan (una o varias llamadas, en orden) que pasa por el mismo ejecutor que el router (SafetyGuard, confirmaciones, deshacer y registro); para una pregunta, texto a trozos con la línea `[dato | contexto]` para la burbuja.
  - El ejecutor hace las esperas: tras abrir una app, si el paso siguiente usa su ventana, espera a que aparezca (`wait_for_window`). Un plan con parámetros no válidos se reintenta una vez con el error.
  - Lo que el router no encuentra pasa al LLM con los candidatos más parecidos como pista. El LLM sabe cuál es la ventana activa («ciérrala»).
  - Si el modelo escribe la llamada como texto (`close_app({...})`), se convierte en plan en vez de leerse en voz alta. Si se salta la frase hablada o el «]», se dice el dato de la burbuja.
  - Rutas «Carpeta/Subcarpeta» («crea Fondos en Imágenes y mueve allí las fotos»). `find_files` busca por extensión («los pdf de Documentos»). «Pon música» va por el router.
  - Contexto de 8192 tokens (las herramientas ocupan ~3.400). La hora y la ventana activa van con el mensaje del usuario para que el prompt de sistema y las herramientas sigan en la caché de Ollama: la primera petición baja de 2,4 s a 0,8 s.
  - Alarmas, temporizadores y recordatorios: `set_alarm` y `set_timer` (verdes, permitidos en partida, con texto opcional para recordar algo y deshacer = cancelar). Guardados en SQLite (`%LOCALAPPDATA%\Nyx\alarms.db`); al sonar, burbuja con «Parar», timbre cada 2,5 s durante un minuto como mucho, la frase («Son las 10:50.») y notificación de Windows. Se callan con «Parar», al hablarle a Nyx o con «Nyx, para» (que entonces no pausa la música). Las que vencen con Nyx cerrado se avisan una sola vez al arrancar.
  - Router: «temporizador de 5 minutos», «avísame en media hora», «pon una alarma a las 7 y media», «a las 5 de la tarde», «despiértame mañana a las 8».
  - Protocolo v4: la burbuja lleva `alert` (notificación de Windows con `tauri-plugin-notification`).
  - Tras la primera prueba de la 3c: el reescaneo automático (al instalar apps o crear carpetas) fallaba en el escáner de apps por no inicializar COM en su hilo y guardaba la caché sin apps («no encuentro Spotify», «no encuentro el bloc de notas»). Ahora se inicializa, una fuente que falla conserva sus entradas anteriores y, si la caché no tiene apps, se reescanea al arrancar. Las llamadas que el modelo escribe tras una cabecera («[acciones]» + `set_timer(...)`) ya no se leen en voz alta. Si lo que se pide abrir no se parece a nada, se dice «No encuentro X» sin pasar por el LLM.
  - Tras la segunda prueba: «Reiniciar núcleo» solo mataba `uv` y el núcleo anterior seguía escuchando, así que cada frase se atendía dos veces (una con código viejo: comandos leídos en voz alta, «para» que pausaba Spotify además de parar la alarma). La app mata ahora el árbol entero y el núcleo cierra al arrancar cualquier núcleo anterior (`core.pid`).
  - `send_hotkey` (amarilla, bloqueada en partida, lista de atajos prohibidos: Alt+F4, Mayús+Supr, Supr, Win+R, Win+X, Win+L, Ctrl+Alt+Supr…), adelantada de la fase 6. Router: «abre una pestaña nueva (en el bloc de notas)» → Ctrl+T en su ventana, o abrirla si no lo está.
  - Volumen por app relativo («sube el volumen de Spotify») y en el router. «Siguiente canción en Spotify» por el router. Alias sacados de la ruta del ejecutable («Riot Client» para «Cliente de Riot»); la caché se rehace sola si cambia la versión del escaneo.
  - Los avisos de alarmas y temporizadores duran 5 s (timbre y burbuja); la burbuja de «Temporizador puesto» también se va a los 5 s («deshaz» sigue valiendo 30 s).
  - La voz lee las cifras en palabras: «1, 2, 3» → «uno, dos, tres», «21:36» → «veintiuna y treinta y seis», «50 %» → «cincuenta por ciento», «3,5» → «tres coma cinco», «18 °C», «€», «x», «=». Antes Pocket TTS las leía mal («cuenta del 1 al 10» sonaba en otro idioma). La burbuja sigue con cifras.
  - Acciones dentro de las apps (`app_action`): catálogo por app con atajos según el idioma de Windows (Bloc de notas, navegadores, Spotify, Discord, Explorador, VS Code, Word, Excel). «Sube el volumen de Spotify» mueve el volumen propio de Spotify y devuelve el foco. `send_hotkey` y `app_action` se niegan dentro de los juegos.
  - `docs/ACCIONES.md`: catálogo de todo lo que Nyx hace y hará.
  - Atajos aprendidos: si el LLM resuelve una frase con una sola acción y sale bien, la siguiente vez se hace sin LLM (`%LOCALAPPDATA%\Nyx\shortcuts.db`). Deshacer justo después lo olvida. No se aprende lo rojo ni lo que depende del momento («ciérralo», «esto», acciones sin app).
  - Negativas fijas antes del router: vaciar la papelera, borrar «para siempre» y cualquier acción dentro de un juego («escribe en el chat del Valorant»).
  - Router: guardar, pantalla completa, aleatorio, repetir, me gusta, dos ventanas a la vez; «busca X en Discord» ya no se toma por una carpeta; «y maximízalo» se reconoce como segundo paso.
  - Batería de frases (`core/tests/battery/frases.jsonl`, `uv run python scripts/battery.py`): 99 frases, 100 % de acierto (router 69/69 al instante; LLM 28/28, mediana 0,55 s). Informe en `docs/benchmarks/bateria-3c.md`.
- Fase 3b (cerrada): archivos, SafetyGuard, confirmaciones, deshacer y registro.
  - Herramientas: `create_folder`, `list_files`, `find_files` (Everything o índice de Windows), `move_files`, `copy_files`, `rename_file` (amarillas, con deshacer), `delete_files` (roja, siempre a la papelera) y `close_app` (amarilla; roja con cambios sin guardar; nunca mata el proceso), más `undo`.
  - SafetyGuard con reglas fijas: rutas protegidas (sistema, raíces de disco, Nyx, carpetas principales del usuario), confirmación solo con clic si son más de 50 archivos o algo fuera de la carpeta del usuario. Nunca se sobrescribe un archivo: «nombre (2)».
  - Confirmación en la isla con botones Confirmar / Cancelar y por voz («sí», «vale», «adelante» / «no», «cancela», «espera»), con 15 s de plazo. La isla recibe clics solo mientras muestra botones.
  - Deshacer durante 30 s con el botón de la burbuja o «Nyx, deshaz».
  - Registro de acciones en `%LOCALAPPDATA%\Nyx\actions` (un archivo por día, 30 días).
  - Borrar también se puede deshacer 30 s: se recupera de la papelera («deshaz», «recupéralo» o el botón).
  - La isla atraviesa los clics salvo con el ratón encima de un botón: Rust mira el ratón cada 30 ms y la página le dice dónde están los botones.
  - Router: deshacer, cerrar, crear carpetas, mover/copiar/borrar «los últimos N archivos de X», borrar una carpeta, buscar y listar. Protocolo v3 (botones en las burbujas).
- Fase 3a (cerrada): caché del sistema, router rápido y herramientas verdes.
  - Caché SQLite en `%LOCALAPPDATA%\Nyx\cache`: apps de Inicio y de la Store (shell:AppsFolder), juegos de Steam, Riot y Epic, carpetas del usuario y su primer nivel, páginas de Configuración y webs frecuentes. Alias automáticos («vscode», «el lol», «balorant»), búsqueda difusa en ~1 ms y desempate por uso. Se reescanea al instalar apps o crear carpetas (watchdog) y cada 24 h.
  - Router rápido sin LLM: abrir apps, juegos, webs, carpetas y páginas de Configuración; volumen (general y por app), silencio, multimedia, capturas, maximizar/minimizar/media pantalla/otro monitor y cambiar de ventana. «No encuentro X» con sugerencia.
  - 10 herramientas, cada una con su archivo, esquema, riesgo, política en partida y pruebas: `open_app`, `focus_window`, `window_layout`, `wait_for_window`, `open_url`, `open_settings`, `open_path`, `set_volume`, `media_control`, `screenshot`.
  - Ejecutor con validación de parámetros, tiempo máximo por herramienta y planes que se detienen en el primer fallo; hasta el bloque 3b solo ejecuta herramientas verdes.
  - Lo que Nyx abre sobrevive a Nyx (sale de su job object) y recibe el foco en cuanto aparece su ventana, salvo «en segundo plano», «sin enfocar», «de fondo»…
  - Escucha: en cada pausa de ~0,4 s se transcribe lo dicho; si ya es una petición completa, Nyx deja de escuchar y responde a eso (y antes). La ventana de seguimiento solo acepta frases nuevas tras un silencio, ignora coletillas y, si no es una orden clara, pregunta al LLM si va dirigida a Nyx (14/15 aciertos en pruebas, ~250 ms).
- Fase 2 (cerrada el 2026-11-09): bucle de voz.
  - Micrófono por WASAPI (16 kHz mono, bloques de 32 ms, 2 s de pre-grabación; se reabre si deja de dar audio). Dispositivos por nombre en los ajustes.
  - Activación provisional con Vosk (gramática con «nix» y palabras parecidas) y Silero VAD con corte a los 700 ms de silencio (máximo 15 s).
  - whisper-server residente con Vulkan: elige la GPU por nombre, transcripción de calentamiento al arrancar y relanzamiento si se cae. Limpieza del texto: quita «Nyx», descarta alucinaciones de Whisper y normaliza horas («a las diez cincuenta» → 10:50).
  - Cerebro con Ollama: prompt fijo + memoria corta (6 turnos, 10 min) + fecha y hora; respuesta `{spoken, display, secondary}` leída a trozos; prefijo del prompt precargado al arrancar; avisos claros si Ollama no está, falta el modelo o se atasca (8 s).
  - Voz con Kokoro (`ef_dora`) por frases mientras el LLM genera; se corta al decir «Nyx» o con una petición nueva. Ventana de seguimiento de 5 s.
  - Entrada por texto (`Win+Alt+N`) y atajo de hablar (`Win+Alt+H`, toque o mantener). Protocolo v2.
  - Ajustes en `%APPDATA%\Nyx\settings.json` con versión y valores por defecto. `nyx --download-models` (huella SHA-256) y `nyx --ask`.
  - Los procesos hijos del núcleo (whisper-server) mueren con él aunque se cierre de golpe (job object de Windows).
  - Segunda verificación de «Nyx» con whisper (adelantada de la fase 4): descarta las activaciones falsas («no existe», canciones) sin decir nada. Vosk tiene más palabras parecidas en su gramática («no», «existe»…).
  - Las peticiones escritas se responden solo en la burbuja, con la respuesta entera; el ajuste `responses.speak_typed` hace que también se digan en voz alta.
  - Si Ollama no está abierto, Nyx lo abre y repite la petición (sigue abierto al salir de Nyx). En Windows un puerto cerrado tarda ~2 s en rechazar: ya no se confunde con «atascado».
  - Latencia medida en el PC de referencia, del fin de la frase a la primera palabra: ~0,8–1,1 s (stt 0,17 s, primer token 0,1 s, primera frase de Kokoro 0,3–0,6 s).
- Especificación en `docs/SPEC.md`, con la sección 18 (decisiones tomadas).
- Estructura del repositorio según la sección 16: `core/` (paquete `nyx` con un subpaquete por servicio), `ui/` y `docs/`.
- `CLAUDE.md` con las reglas de trabajo y las decisiones tomadas.

### Cambiado (voz)

- Piper sustituye a Kokoro: voz predeterminada de mujer con acento de España (sharvard F); davefx (hombre, España) y daniela (mujer, Argentina) en `tts.voice`. ~0,04 s por frase: del fin de la frase a la voz, ~0,3 s (antes 0,8–1,1 s). Los ajustes con voces de Kokoro se migran solos. Prueba de escucha en `docs/benchmarks/tts-TomPi-20261109.jsonl`.

- Voz predeterminada «lola» con Pocket TTS (Kyutai): sharvard F sonaba robótica. La voz se reproduce a trozos según se genera (primer audio en ~0,08 s; del fin de la frase a la voz, ~0,4 s). davefx y daniela (Piper) siguen disponibles en `tts.voice`. Los modelos de Pocket se guardan en `%LOCALAPPDATA%\Nyx\models\hf` y `nyx --download-models` los descarga.

### Corregido

- El núcleo se colgaba al cargar Pocket TTS lanzado desde la app: en Windows, la lectura pendiente de stdin (para saber si la app había muerto) bloqueaba otra consulta que hace PyTorch al cargar. Ahora la app le pasa su PID (`NYX_PARENT_PID`) y el núcleo lo vigila cada segundo.

- La isla perdía `WS_EX_NOACTIVATE` y `WS_EX_TOOLWINDOW` al arrancar y se ocultaba al mostrar botones: `set_ignore_cursor_events` de Tauri reescribe todos los estilos según lo que tao cree de la ventana (que estaba oculta, porque se muestra con Win32). Ahora el paso de clics se cambia directamente con Win32. La ventana de texto recupera `WS_EX_TOOLWINDOW` después de que tao la muestre.
- Router: «a la carpeta de Documentos» ya se entiende como «Documentos».

### Cambiado

- `npm run tauri dev` ya no lanza el núcleo en modo demo: arranca el bucle de voz real (`NYX_DEMO=1` para la demo).

- Cristal: el Acrylic de Windows queda descartado (se ve sólido en ventanas sin foco y actualiza lo de detrás con unos 2 s de retraso). La isla y las burbujas usan un tinte gris translúcido al 84 % en CSS, que cambia en el mismo fotograma que el fondo (medido: menos de 25 ms, también con Chrome). El cristal con desenfoque real queda para un motor propio más adelante.
- SPEC: sin cuenta de usuario; datos de uso anónimos solo con permiso (sección 8); interfaz en ventanas flotantes propias en lugar de capa a pantalla completa, con elección de monitor según ajustes y modo partida (secciones 9 y 11); Svelte 5 y `uv` en el stack (sección 2); repositorio público desde la fase 6 (sección 15).
