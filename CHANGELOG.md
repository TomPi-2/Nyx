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
