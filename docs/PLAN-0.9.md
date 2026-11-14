# Plan de la versión 0.9 — Beta pública (parte adelantada)

> **Borrador de Claude del 2026-11-14**, escrito sin el usuario con su permiso («puedes ir
> avanzando las siguientes fases como crear el instalador, las actualizaciones automáticas, la
> gestión de extensiones y la animación de onda»). Solo cubre esas partes; el resto de la 0.9
> (primer arranque como conversación, datos anónimos, soporte, voz propia, beta) se planifica
> al llegar. Funciona como los planes de la 0.6 y la 0.7: una tarea por sesión, sus
> comprobaciones, un commit y su fila en el Registro. **Lo visual se enseña antes en un
> prototipo HTML y no se integra sin el visto bueno del usuario.**
>
> Fuentes: SPEC §2 (empaquetado), §11 y §12 (ventanas y cristal), §15 (actualizaciones);
> [INSTALADOR-Y-MOTOR-GRAFICO.md](INSTALADOR-Y-MOTOR-GRAFICO.md) §3 y §4;
> [HOJA-DE-RUTA.md](HOJA-DE-RUTA.md) §2 (0.9) y §11.

## 0. Decisiones ya tomadas por el usuario

- Instalador propio, sin bordes, con el estilo de Ajustes y animaciones propias; al acabar, la
  onda de cristal sale de él (2026-11-10).
- Velopack para instalar y actualizar desde GitHub Releases, con deltas, cambio atómico y vuelta
  atrás (SPEC §15).
- Si falta Ollama, el instalador instala el oficial en silencio (2026-11-14).
- Indicador de «Nyx listo»: **onda** por defecto; también «Nyx aparece y desaparece» o nada
  (2026-11-14). En partida, con «reducir movimiento», cristal en Bajo o sin captura: el
  cuadrado.
- Las animaciones del instalador las propone Claude en un prototipo (2026-11-14).

## 1. Tareas

| Tarea | Qué | Necesita al usuario |
| --- | --- | --- |
| 9.01 | **Prototipo del instalador** (`docs/prototipos/instalador.html`): pasos (bienvenida, licencia GPL-3.0, carpeta, componentes y espacio, descarga con progreso real por partes, preparación del cerebro y la voz, listo) y sus animaciones, con la onda al final. | Verlo y aprobarlo |
| 9.02 | **Prototipo de la onda de «Nyx listo»** (en el mismo archivo o `onda.html`): la onda que recorre todos los monitores como uno y la alternativa del cuadrado. | Verlo y aprobarlo |
| 9.03 | **Ajuste «Indicador de Nyx listo»** (Apariencia: Onda · Nyx aparece y desaparece · Nada; por defecto Onda) en el núcleo, la interfaz y la SPEC §13. | — |
| 9.04 | **Onda real**: una ventana transparente por monitor (siempre encima, sin foco, deja pasar los clics), mismo reloj, la onda en coordenadas del escritorio virtual; existen solo 1–2 s. Al arrancar Nyx cuando ya está listo y al acabar el instalador. Tras el visto bueno de 9.02. | Probarla |
| 9.05 | **Actualizaciones, parte del núcleo**: ajuste (Preguntar · Automático · Solo avisar; canal estable o beta), «momento adecuado» (sin petición, partida, grabación, archivos ni confirmación pendientes), copia de seguridad de ajustes y bases de datos antes de actualizar y migraciones versionadas que restauran la copia si fallan. Con pruebas. | — |
| 9.06 | **Actualizaciones, parte de la app**: Velopack en la app Tauri (crate `velopack`, MIT: comprobar al arrancar y cada 6 h, descargar con prioridad baja, aplicar cuando el núcleo dice que es buen momento, avisos en la isla y vuelta atrás). | Probar con una versión de verdad (necesita el repositorio público y una Release) |
| 9.07 | **Empaquetado del núcleo** sin `uv` en el equipo del usuario: Python «embeddable» oficial + dependencias instaladas al construir (como prevé la 7.05 para las extensiones) o Nuitka/PyInstaller. Medir tamaño y arranque. | Permiso para descargar el Python oficial (ver 7.05) |
| 9.08 | **Instalador real** (`installer/`, app Tauri pequeña, sin administrador, en `%LOCALAPPDATA%`): lanza Velopack en silencio, Ollama oficial si falta, descarga de modelos con SHA-256 y reanudación, calentamiento y la onda. Tras 9.01, 9.06 y 9.07. | Probarlo en el PC y el portátil |
| 9.10 | **Primer arranque guiado por Nyx** (decisión del usuario, 2026-11-14; SPEC §13): el instalador se recoge en un panel de descargas arriba a la derecha y Nyx configura con paneles propios, empezando por el micrófono para poder contestar hablando, su color, su tamaño y el tinte (con los nombres visibles), el escaneo (con Everything si se marcó en el instalador) y los datos anónimos, con cambios al instante y comentarios. Sustituye al asistente actual. Prototipo aprobado el 2026-11-14. | Probarlo |
| 9.11 | **Paneles de ajuste por voz**: «Nyx, quiero cambiarte el color» (o el tamaño, o el color de los paneles) saca el mismo panel del primer arranque junto a Nyx en vez de abrir Ajustes. Router y herramienta nueva. | Probarlo |
| 9.09 | **Publicación** (GitHub Actions): etiqueta `v…` → compilar, empaquetar con Velopack, firmar (SignPath) y subir a Releases. | El repositorio público («publícalo») y SignPath |

**Sin el usuario se puede hacer:** 9.01, 9.02 (prototipos), 9.03 y 9.05; preparar 9.04 tras
el visto bueno. Lo demás necesita descargar herramientas (Velopack `vpk`, Python oficial), una
Release publicada o probar en los dos equipos.

## 1b. Plan de construcción (aprobado por el usuario el 2026-11-14)

Prototipo aprobado; esto es el orden y los archivos para construirlo de verdad. Primero lo
que se prueba en el PC sin instalador (el primer arranque dentro de la app) y al final lo que
necesita una Release.

1. **9.10a Primer arranque en la app** (sin instalador: se lanza con `nyx --primer-arranque`
   o desde Ajustes → Ayuda, y sale solo la primera vez).
   - Núcleo: `nyx/setup/flow.py` (los pasos en el orden aprobado: bienvenida, micrófono, color,
     tamaño, tinte, escaneo, datos; textos con variantes; avanzar, volver, saltar, callarse al
     pasar de paso con un fundido de 150 ms en `nyx/tts`), `nyx/setup/answers.py` (entender
     las respuestas habladas: colores y tintes por su nombre, «más grande», «120», «siguiente»,
     «atrás», «sí/no»; lo usa también la 9.11) y `nyx/setup/downloads.py` (lo que falte: voz,
     Ollama oficial en silencio y el cerebro con `/api/pull`, con progreso, reanudación y
     SHA-256; luego cargar y probar el cerebro). Ajuste `first_run_done`.
   - Protocolo v19 (`protocol.py` y `protocol.ts` a la vez): `setup_step`, `setup_choice`,
     `setup_downloads`, `setup_done`.
   - Interfaz: `ui/src/setup/` con un panel por paso (`Welcome`, `Mic`, `Color`, `Size`,
     `Tint`, `Scan`, `Data`) dentro de la ventana de paneles de siempre, bajo Nyx;
     `lib/controls/NamedSwatches.svelte` (muestras con nombre y el anillo de Ajustes);
     `routes/descargas/+page.svelte` (el panel de descargas arriba a la derecha) y su ventana
     en `src-tauri` (`setup.rs`). El asistente de ahora (`onboarding/`) queda como respaldo
     hasta que esto funcione y luego se quita.
   - Pruebas: `tests/test_setup_flow.py`, `tests/test_setup_answers.py`.
2. **9.11 Paneles por voz**: regla del router y herramienta `nyx_panel` («quiero cambiarte el
   color», «hazte más grande», «cambia el color de los paneles») que saca el mismo panel junto
   a Nyx; con `answers.py`.
3. **9.04 Onda real**: una ventana transparente por monitor (`src-tauri/src/wave.rs` y
   `routes/onda/`), mismo reloj, coordenadas del escritorio virtual; al acabar el primer
   arranque y al encender si está elegida.
4. **9.07 Empaquetado del núcleo** con el Python embeddable (sin `uv` en el equipo del
   usuario). **Decidido por el usuario (2026-11-14):** el núcleo pasa a Python 3.14 aquí (la
   3.12 ya no publica binarios con parches); antes, comprobar que todas las dependencias
   tienen ruedas para ella y medir.
5. **9.06 Velopack en la app** (`vpk`, MIT) y **9.08 instalador** (`installer/`, app Tauri
   pequeña con las pantallas aprobadas: bienvenida, licencia, opciones con Everything y acceso
   directo apagados, instalación de la app y la voz; luego abre Nyx con `--primer-arranque` y
   se recoge hacia la esquina, donde aparece el panel de descargas de la app). Probar en el PC
   y el portátil.
6. **9.09 Publicación**, cuando el repositorio sea público.

## 2. Gestión de extensiones (0.7, tarea 7.11)

La parte del núcleo está hecha (7.01–7.04 y 7.08). La pantalla de Ajustes → Extensiones va
primero como prototipo (`docs/prototipos/extensiones.html`): lista con permisos a la vista,
activar, desinstalar, actualizar, modo desarrollador y la etiqueta «sin revisar».

## 3. Registro

| Tarea | Agente | Commit | Notas para la revisión | Revisado |
| --- | --- | --- | --- | --- |
| 9.01 y 9.02 (prototipo) | Claude | `843cf45` | `docs/prototipos/instalador.html`: bienvenida (Nyx respira), licencia libre explicada en tres líneas (sin «aceptar»), qué se instala con tamaños y espacio libre, instalación con barras líquidas y la forma de Nyx que se llena con el total, corte de red (pausa y sigue donde iba), preparación (cerebro en la gráfica, oído, voz) y final: el panel se recoge en Nyx y sale la onda, que cruza dos monitores de distinto tamaño con el mismo reloj. Alternativas «Nyx aparece y desaparece» y «Nada», y la onda al encender el PC. **Visto por el usuario (2026-11-14): le gusta.** Corregido: el tick parpadeaba (cada repintado, cada 120 ms, volvía a animar el tick, el brillo de las barras y el oleaje: ahora la pantalla se pinta una vez y solo cambian los números); acceso directo en el escritorio, opción apagada en «Opciones»; el primer arranque (conversación guiada) empieza en cuanto están la app y el oído y la voz, que bajan antes que Ollama y el cerebro. **Rehecho tras su segunda revisión (2026-11-14):** el primer arranque deja de ser un panel del instalador (ver 9.10); Everything y el acceso directo, opciones del instalador apagadas por defecto. Tercera versión (micrófono primero, nombres visibles, deslizador y etiquetas propias). **Aprobado por el usuario el 2026-11-14** («me encanta, adelante con el instalador y el arranque»). | |
| 9.10a | Claude | `bbd2cf3` y (este commit) | Núcleo: `nyx/setup/flow.py` (`GuidedSetup`: pasos en el orden aprobado, textos y reacciones del prototipo, cambios por `SettingsRequested` como Ajustes, prueba del micrófono con el nivel y «Nyx», escaneo con Everything, datos sin marcar, despedida distinta si aún baja algo; `start("color"|"size"|"tint")` para la 9.11; espera a que la voz esté lista), `nyx/setup/answers.py` (respuestas habladas sin el cerebro), `Player.fade_out` (150 ms, solo lo que sonaba), `Pipeline.announce`/`hush` (callarse al pasar de paso o al oírte), lo oído o escrito va al primer arranque (también «Nyx» como prueba), tras probar el micrófono escucha 8 s sin «Nyx», `AudioCapture.switch` (el micrófono elegido se usa ya), protocolo **v19**. Interfaz: `setup/SetupPanel.svelte` (en la ventana de paneles, bajo Nyx; texto que se escribe mientras habla), `MicStep`, `ScanStep`, `lib/controls/NamedSwatches.svelte` (nombres visibles y el anillo de Ajustes), `Slider` con etiqueta del valor al arrastrar, `setup/Downloads.svelte` en una tercera ventana flotante arriba a la derecha (`downloads`, `place_top_right_at`), Nyx a la vista todo el rato («esperando» en reposo), la isla lo empieza si no se ha hecho y Ajustes → Ayuda → «Repetir» también. El asistente viejo (`onboarding/`) queda sin usar hasta que lo pruebe el usuario. Pruebas: `test_setup_guided.py` (30). Capturas de cada panel comprobadas. **Falta: probarlo el usuario en la app.** | |
| 9.10a (tanda) | Claude | `6d3bcd2` | Tras la primera prueba del usuario (ERRORES.md, 2026-11-14): no se activa con su propia voz (`Pipeline._announce_barge` + `stt.normalize.is_echo`, sin tocar el umbral); escucha sin «Nyx» todo el rato mientras dura (`SETUP_LISTEN_S`, vuelve a escuchar si no hay voz; deja de escuchar mientras habla); `_is_complete` con `setup.understands`; pista a whisper con las palabras del paso (`answers.vocabulary`); «pequeño» en masculino, nombres parecidos (≥ 80 % o el final de uno largo) y «termin…»; altavoces en el paso del micrófono (`Player.switch`, protocolo **v20**). pytest 1.796. | |
| 9.04 | Claude | `87d7a78` | `src-tauri/src/wave.rs` (`wave_play`: una ventana `onda-N` por monitor, sin foco, que deja pasar los clics, siempre encima; origen en el sitio de Nyx aunque esté oculta, `island::current_area`; mismo reloj con 0,8 s de margen; alcance hasta la esquina más lejana del escritorio virtual) y `routes/onda` (anillo del motor de cristal que se adelgaza al crecer; si el motor solo tiñe, no se dibuja; sin motor, anillo de luz CSS; se cierra sola). Motor: forma con `ring` (grosor del anillo, `gParams.z` en `glass.hlsl`). Núcleo: evento `NyxReady` → `nyx_ready` (v20) al arrancar con el primer arranque hecho, y al acabarlo cuando ya no baja nada. La isla decide: onda, o Nyx aparece 1,8 s («nyx», o en partida, «reducir movimiento», cristal en Bajo o «salir en capturas»). Ajustes → Apariencia → «Probar». Shader compilado con `fxc`; clippy y svelte-check sin avisos; pytest 1.797. **No probado en pantalla: lo prueba el usuario.** | |
| 9.11 | Claude | `b940266` | Herramienta `nyx_panel` (verde, en partida al terminar, **solo para el router**: `llm_visible = False`, así no cambian las herramientas del modelo entrenado) que pide al flujo guiado el panel suelto (`SetupFlowRequested("start", "color"|"size"|"tint")`). Router: `nyx_change` con color o tamaño y la regla nueva `nyx_panel` («cámbiate el color», «cambia el color de los paneles»…) sacan el panel; `nyx_size` («hazte más grande», «ponte un poco más pequeño») cambia el tamaño directo (antes iba al modelo). Panel suelto: solo se queda con lo que entiende; lo demás lo cierra sin decir nada y lo atiende Nyx como siempre (`GuidedSetup.wants`/`dismiss`); se cierra solo a los 45 s sin usarlo; «listo» sin cambios no dice «me encanta». Mientras habla el panel, la canalización no abre la ventana de seguimiento encima. pytest 1.818. | |
| 9.07 | Claude | `93c484d` | **Núcleo a Python 3.14** (decisión del usuario): todas las dependencias tienen ruedas para 3.14 (nada se compila); mismos 119 paquetes en `uv.lock`; 1.818 pruebas pasan; medido igual o algo mejor (voz 4,5× tiempo real frente a 4,46×, carga de la voz 4,2 s frente a 4,45 s, import del núcleo 0,53 s; router 0,15 ms por frase). `requires-python`, ruff (`py314`, salvo `training/llm` y los módulos MIT del kit, que siguen en `py312`) y mypy. `core/scripts/package_core.py`: Python embeddable oficial (mismo zip y huella que las extensiones), dependencias de `uv.lock` con `--require-hashes` en `Lib\site-packages`, `python314._pth` con `..pp` e `import site` (pywin32), el núcleo en .pyc, `build.json`, la carpeta vieja a la papelera y prueba de humo (importa torch, onnxruntime, pocket_tts, piper, pywin32, WinRT y `python -m nyx --help`). Resultado: 1.010 MB, 92 s. Probado: `python -I -m nyx --ask` con el empaquetado responde (742 ms). `core_process.rs` lanza `core\python\python.exe -I -X utf8 -m nyx` si está junto al ejecutable; si no, `uv run` (desarrollo). | |
| 9.06 | Claude | `28bd828` | App: crate `velopack` (MIT); `main.rs` empieza con `VelopackApp::build().run()` (ganchos de instalación y aplica al abrir una versión descargada y no aplicada); `updater.rs`: `GithubSource` del repositorio oficial (beta = también «pre-release»), comprueba al arrancar (cuando la isla dice el canal) y cada 6 h, descarga en un hilo en modo de fondo de Windows y avisa a la isla (`update://ready`); `update_apply` para el núcleo (`core_process::stop`, sin relanzarlo) y `apply_updates_and_restart`. La versión del núcleo es la de la app (`NYX_APP_VERSION`). Núcleo: `update/coordinator.py` decide (Preguntar con [Ahora]/[Más tarde] cada 4 h, Automático con 10 min sin usar el PC, Solo avisar con [Actualizar]; siempre con `UpdateGate`), copia los datos y pide aplicar (protocolo **v21**: `update` y `update_apply`); al arrancar la nueva, «Actualizada a la X» (`Outcome.updated_from`). pytest 1.823, clippy y svelte-check sin avisos. **Sin probar con una versión de verdad** (necesita el repositorio público y una Release). Dudas en `REVISAR.md` (17). | |
| 9.08 | Claude | (este commit) | `installer/` (Tauri 2 + Svelte, sin administrador): bienvenida, licencia en tres líneas, opciones (Everything y acceso directo apagados, arrancar con Windows encendido, espacio libre real) e instalación con progreso real; la ventana mide lo que su tarjeta y al acabar se recoge hacia arriba a la derecha y abre Nyx. Rust: Setup de Velopack del lado del instalador o descargado de la última Release y comprobado con `SHA256SUMS.txt` (solo HTTPS), `--silent` en `%LOCALAPPDATA%\TepnyxNyx`; `instalador.json` (Everything), clave Run y `Nyx.lnk`; el oído y la voz con el núcleo instalado (`python -m nyx --download-models --json`). App: si la abre el Setup durante la instalación se cierra (la abre el instalador), y al desinstalar quita la clave Run y el acceso directo. Núcleo: Ollama oficial con winget en el panel de descargas antes del cerebro (`setup/ollama.py`), Everything si se marcó, `whisper-server` empaquetado en `core\bin\whisper`. `scripts/build-release.ps1`: núcleo, app, `vpk pack` (herramienta local, 1.2.161), huellas e instalador en `Releases\<versión>`. Construido de punta a punta con una 0.9.0 de prueba: Setup 341 MB (el núcleo de 1 GB comprimido), instalador 4,1 MB; el núcleo arranca desde el paquete. **Sin probar la instalación de verdad en tu PC** (instalaría Nyx al lado del de desarrollo): pruébalo en el portátil. Dudas en `REVISAR.md` (18). | |
| 9.03 | Claude | `7938d43` | `appearance.ready_indicator` (onda · nyx · nada; por defecto onda) en el modelo de ajustes, el saludo del puente (protocolo **v18**, los dos lados) y Ajustes → Apariencia («Al estar lista», con la explicación de cada opción); SPEC §13. La onda en sí es la 9.04 (tras el visto bueno del prototipo). pytest 1.707, svelte-check sin errores. | |
| 9.05 | Claude | `aea9f93` y (este commit) | `nyx/update/`: `backup.py` (copia de ajustes, `extensions.json`, cola de la partida, ventana de Ajustes y las bases de alarmas y atajos con la API de copia de SQLite, cerrando las conexiones; restaurar manda los `-wal`/`-shm` viejos a la papelera; se quedan 3 copias y las demás a la papelera), `migrations.py` (versiones número a número; al arrancar, si la versión sube y hay migraciones de ese tramo: copia, las aplica en orden y, si una falla, restaura y no apunta la versión; al bajar no migra; hoy la lista está vacía), `moment.py` (`UpdateGate`: pipeline libre y sin botones pendientes, sin partida ni cola). Ajustes `updates.mode` y `updates.channel` (editables) en Ajustes → General; `main.py` migra antes de leer los ajustes. Encontrado: `with sqlite3.connect()` no cierra la conexión (en Windows la copia no se podía mover). Falta quien pregunte al `UpdateGate`: la app con Velopack (9.06). pytest 1.715. | |
