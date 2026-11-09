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

### Cambiado

- `npm run tauri dev` ya no lanza el núcleo en modo demo: arranca el bucle de voz real (`NYX_DEMO=1` para la demo).

- Cristal: el Acrylic de Windows queda descartado (se ve sólido en ventanas sin foco y actualiza lo de detrás con unos 2 s de retraso). La isla y las burbujas usan un tinte gris translúcido al 84 % en CSS, que cambia en el mismo fotograma que el fondo (medido: menos de 25 ms, también con Chrome). El cristal con desenfoque real queda para un motor propio más adelante.
- SPEC: sin cuenta de usuario; datos de uso anónimos solo con permiso (sección 8); interfaz en ventanas flotantes propias en lugar de capa a pantalla completa, con elección de monitor según ajustes y modo partida (secciones 9 y 11); Svelte 5 y `uv` en el stack (sección 2); repositorio público desde la fase 6 (sección 15).
