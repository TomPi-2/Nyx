# Nyx — instrucciones para Claude

Eres el desarrollador principal de Nyx. La especificación completa está en [docs/SPEC.md](docs/SPEC.md): léela entera antes de escribir código y trátala como fuente de verdad.

## Reglas de trabajo

- Trabaja fase a fase (sección 16). Empieza por la fase 1 y no avances sin que yo lo pruebe y lo apruebe.
- Al empezar cada fase, propón un plan corto con los archivos que vas a crear y espera mi visto bueno.
- Plataforma: solo Windows 11. GPU AMD RX 7700 XT: nada que dependa de CUDA.
- Todo gratuito y local por defecto. Si una librería tiene licencia restrictiva o requiere pago, avísame antes de usarla.
- Cada herramienta: archivo propio, esquema tipado, nivel de riesgo, política de partida y pruebas.
- Nunca bajes los niveles de seguridad de la sección 8 ni uses borrado permanente.
- Código con tipado (mypy/TypeScript estricto), formato automático (ruff, prettier) y comentarios en español donde aporten.
- Si algo de la especificación no es viable o hay una opción mejor, explícalo y propón la alternativa antes de cambiarla.
- La interfaz sigue la sección 12 al pie de la letra: solo grises por defecto (colores y fuentes fijos opcionales en Apariencia), translúcida, todo redondeado y sin bordes. El resto de la personalización queda para la fase 7.
- Mantén [CHANGELOG.md](CHANGELOG.md) y actualiza `docs/SPEC.md` si acordamos cambios.

## Estado

Fase actual: **versión 0.6 — Cerebro** (fase 6a): plan en [docs/PLAN-0.6.md](docs/PLAN-0.6.md), aprobado el 2026-11-11. Se trabaja tarea a tarea según ese plan (una por sesión, con su commit y su fila en el Registro); también lo sigue Gemini (`GEMINI.md`) cuando no hay Claude, y Claude revisa después lo que haya hecho. Hechas por Claude: 6.01–6.04, 6.18, la revisión de 6.08–6.16 y 6.20a. Gemini hizo 6.18b, 6.08–6.12, 6.15 y 6.16 (revisadas). 6.17 hecha: batería de 337 frases, línea base 256/337 (LLM 110/185; el 7B a menudo contesta en texto en vez de actuar). 6.20b hecha (grupos solo cuando no caben; recortar la lista no ayuda al 7B). 6.21 hecha (pasos 1–4: reencaminado +4, línea base 262/337; qwen3:4b, granite3.3:8b y mistral:7b peores). 6.22 (subida automática del umbral, audio opcional) y 6.24 (olvidar atajos, ciudad automática) hechas; 6.25 en curso: router por temas y 6 tandas de reglas (batería con semilla 364/393, 93 %; router 255/255; línea base vigente en PLAN-0.6 regla 0.3). 6.26 y 6.23 hechas (respuestas con variantes por tono; color plano de Nyx y criterio común de los paneles, pendiente de que el usuario lo vea). 6.27: ronda 2 (`nyx-r2:7b`, batería 391/409 sin actuar nunca sin deber) **adoptada** en el PC; ronda 3 (`nyx-r3:7b`) medida: 392/409 y reserva 73/80, pero actúa sin deber una vez y confunde «bloquear» con «apagar» (recomendado seguir con la r2; decide el usuario). 6.19 (cierre): revisión, SPEC y CHANGELOG al día y batería con `nyx-r2:7b` (390/409, 2026-11-14); falta `game_bench.py`, la prueba del usuario y su visto bueno. El 2026-11-14, con permiso del usuario, se adelantó trabajo sin él: Nyx conoce Tepnyx (creador, apps, web y sus pantallas), arreglos de su prueba (panel «Noche», IP real…), **0.7** ([docs/PLAN-0.7.md](docs/PLAN-0.7.md), aprobado): **cerrada por Claude el 2026-11-15** (7.17; batería 388/409), pendiente del visto bueno del usuario: extensiones con código encerradas, Ajustes → Extensiones, kit (`sdk/` MIT y `core/scripts/nyx_ext.py`), guía (`docs/extensiones/README.md`) y las oficiales de OBS y Spotify (`extensions/`, vienen con Nyx firmadas). Las formas de extensión en la interfaz (7.09) y el sistema de modos (7.10) pasan a la 0.8 (`REVISAR.md` 23). **0.8** (organización y seguridad) en curso: plan en [docs/PLAN-0.8.md](docs/PLAN-0.8.md), aprobado el 2026-11-16 salvo la 8.13 (formas de Nyx: extensión, más adelante); hechas 8.01–8.03 y 8.05–8.08; la 8.09 (modos) es una propuesta en [docs/MODOS.md](docs/MODOS.md) que espera al usuario, y después 8.10–8.12; falta la 8.04 (dictado). **0.9** (borrador [docs/PLAN-0.9.md](docs/PLAN-0.9.md)): 9.03 (ajuste de la onda) y 9.05 (copia, migraciones, buen momento) hechas; prototipo del instalador gustado; primer arranque rehecho como configuración guiada por Nyx con paneles propios (9.10, y su reutilización por voz, 9.11); prototipo y plan de construcción (PLAN-0.9 §1b) aprobados el 2026-11-14; 9.10a hecha (primer arranque guiado de verdad en la app) y una tanda de arreglos tras la primera prueba del usuario (su propia voz, escucha continua, «más pequeño», altavoces; protocolo v20); 9.04 hecha (la onda de «Nyx lista», con «Probar» en Apariencia); las dos, pendientes de que las pruebe el usuario. El 2026-11-14 («hazlo todo menos publicar») también: 9.11 (paneles por voz), 9.07 (núcleo en Python 3.14 y empaquetado), 9.06 (Velopack, protocolo v21) y 9.08 (instalador y `scripts/build-release.ps1`); dudas en `REVISAR.md` (16–18). Queda la 9.09 (publicar), que espera al usuario. Bloque D (6.13 y 6.14) hecho; bloque B: 6.05/6.06 hechas (Wikipedia; la API con clave, pendiente del usuario), falta 6.07 (recetas). Lo hecho sin el usuario y sus decisiones pendientes: `docs/REVISAR.md`. Rendimiento en partida medido el 2026-11-13: −3,1 % de FPS, dentro del objetivo. Al empezarla, proponer el plan corto con los archivos y esperar el visto bueno. Las versiones de la hoja de ruta sustituyen a las fases 6 y 7 de la SPEC. Fase 5 (versión 0.5) cerrada el 2026-11-11. Pendiente de la 0.5, sin parar el plan: medir el coste en partida en el portátil (`scripts/game_bench.py`) y probar el modo partida con más juegos (Valorant). Fases 1 y 2 cerradas el 2026-11-09; fases 3 y 4 el 2026-11-10.

## Decisiones tomadas

| Fecha | Decisión |
| --- | --- |
| 2026-11-09 | Nyx será gratis y de código abierto (GPL-3.0 + CLA). El repositorio sigue privado hasta la fase 6. |
| 2026-11-09 | Dos equipos: PC con RX 7700 XT (principal y de referencia) y portátil con RTX 3070 Laptop. Las pruebas de rendimiento se hacen en ambos para fijar los requisitos mínimos. Todo por Vulkan, nada de CUDA. |
| 2026-11-09 | La app Tauri es el proceso principal (bandeja, instancia única) y lanza el núcleo Python como proceso hijo; lo reinicia si se cae. |
| 2026-11-09 | Interfaz: Svelte 5 + TypeScript para la UI y WebGL/Canvas directo para el orbe. |
| 2026-11-09 | Python gestionado con `uv` (Python 3.12; desde el 2026-11-14, 3.14). |
| 2026-11-09 | Sin cuenta. Datos de uso anónimos solo con permiso (SPEC sección 8). |
| 2026-11-09 | Interfaz en ventanas flotantes propias, ocultas en reposo; el monitor se elige según ajustes y modo partida (SPEC sección 11). |
| 2026-11-09 | LLM provisional `qwen2.5:7b`; Whisper large-v3-turbo q5 con Vulkan (0,17 s por frase). |
| 2026-11-10 | Apariencia personalizable en 5c‑2 con opciones fijas (no paletas libres): fuente (Segoe UI Variable, Manrope o Nunito), color de Nyx (19, blanco por defecto) y tinte de los paneles (12, gris por defecto). Valores en `docs/prototipos/apariencia.html`. |
| 2026-11-10 | Motor de cristal propio (SPEC sección 12): niveles Auto/Alto/Medio/Bajo, en partida Bajo sin excepción. Nyx y los paneles en ventanas distintas para que Nyx salga siempre en capturas; «Mostrar Nyx en capturas y directos» pasa los paneles a Bajo. Hueco fijo de 14 px entre Nyx y los paneles. |
| 2026-11-11 | Requisitos tras probar el portátil (SPEC 14, `docs/benchmarks/requisitos.md`): mínimos Windows 11, gráfica dedicada con Vulkan y 8 GB de VRAM, 8 núcleos, 16 GB de RAM y ~8 GB de disco; recomendados 12 GB de VRAM y 32 GB de RAM. |
| 2026-11-11 | Fase 5 cerrada (versión 0.5). Siguiente: 0.6, cerebro. |
| 2026-11-11 | Versiones con SemVer `vMAYOR.MENOR.PARCHE` y cualquier número de cifras en cada parte (v1.0.0, v1.142.245, v23.45.132). Aún no se ponen en el código ni en git. |
| 2026-11-11 | Un solo cerebro en la primera versión: `qwen2.5:7b` (el 14B, 8 veces más lento sin acertar más, no cabe en 8 GB y da tirones en partida). En partida se queda en la gráfica («Sí» o «Solo órdenes»); nunca el procesador (medido en Rocket League). Objetivo: con Nyx pensando cada 8 s, < 5 % de FPS y peor fotograma ≤ 1,5× el del juego solo. |
| 2026-11-11 | Hoja de ruta aprobada (`docs/HOJA-DE-RUTA.md`): 0.5 partida → 0.6 cerebro → 0.7 extensiones → 0.8 organización → 0.9 beta (instalador y primer arranque como conversación con Nyx) → 1.0. Overlay solo como ventana aparte, sin inyectarse; si un servicio no permite algo, Nyx lo dice y ofrece guiar; kit de extensiones con licencia MIT; buscador a valorar en la 0.6. |
| 2026-11-12 | Grupos de herramientas (6.20b): solo se recortan cuando no caben (40 % del contexto); medido que recortar no ayuda al 7B. 6.20c pasa a la 0.7. La 6.20d (contexto 8.192) se descarta mientras haya otra forma de evitar la pérdida de FPS. |
| 2026-11-12 | Si el «no actúa» no se arregla con qwen2.5:7b, se prueba otro modelo del mismo tamaño (6.21). |
| 2026-11-13 | Ciudad automática (6.24): sin ciudad en Ajustes, el tiempo usa la ubicación de Windows (si está activada) con la máxima precisión; las coordenadas van a Open-Meteo y a Nominatim (OpenStreetMap) para el nombre de la ciudad. Se confirmará en el primer arranque (0.9). |
| 2026-11-13 | qwen2.5:7b se queda (otros modelos peores). El router resuelve todo lo seguro, con respuestas fijas de varias variantes; el LLM, lo ambiguo y la conversación. LoRA del 7B entrenado en el PC con ROCm (Windows → WSL2); el portátil con CUDA solo como último recurso, y nunca CUDA ni ROCm en Nyx. |
| 2026-11-13 | LoRA (6.27): se adopta la ronda 2 (`nyx-r2:7b`) aunque rompe 8 frases leves; la ronda 3 las corrige. Por defecto sigue `qwen2.5:7b` hasta que el instalador (0.9) pueda descargar el GGUF y crearlo en Ollama. |
| 2026-11-13 | `run_powershell`: excepción verde para una lista cerrada de consultas de solo lectura (SPEC §7 y §8). Permiso para usar llama.cpp (MIT) en el entrenamiento, para exportar el LoRA a GGUF. |
| 2026-11-14 | A «¿quién te ha creado?» Nyx contesta «Tepnyx». Nyx conoce todo Tepnyx y navega por ello: la web (tepnyx.com, código en `../Decider/tepnyx_website`), sus propias pantallas y las otras apps (Decider, Sorty). Instalador (0.9): instala Ollama oficial en silencio si falta; indicador de «Nyx listo» por defecto: onda. Sin el usuario, Claude avanza la 0.7 y partes de la 0.9 (instalador, actualizaciones, onda) y decide 7.05, 7.08, 7.10 y las animaciones del instalador con lo medido, apuntándolo en `REVISAR.md` para que lo confirme. |
| 2026-11-15 | Voz propia de Nyx: sustituye a «lola» (y será la única voz de Nyx por ahora). La graba ella en su equipo con lo que le pase el usuario, lo más sencillo posible (no sabe mucho de ordenadores), en llamada de Discord con el usuario dirigiendo (repetir, entonación); muchas horas; su micrófono suena limpio y Claude limpia lo que haga falta. El contrato lo revisa el abogado (listo la semana del 2026-11-16); se puede ir preparando. Páginas de Nyx y de errores en la web de Tepnyx, al final. |
| 2026-11-14 | Primera versión pública: **0.9.0 (beta)**. Códigos de error para el usuario (`docs/CODIGOS-DE-ERROR.md`, explicados en `tepnyx.com/nyx/errores`). El instalador con el cristal del motor (si la gráfica puede, borde siempre en movimiento) y la forma real de Nyx, sin girar, llenándose con lo instalado. Después: preparar la grabación de la voz de Nyx y la prueba larga de la beta. |
| 2026-11-14 | Firma confirmada: clave `tepnyx-1`, la privada en `%LOCALAPPDATA%\Tepnyx\keys\`. Modo Noche abre Configuración. `ext/manifest.py`, `content.py` y `signing.py` también MIT (kit de extensiones). Extensiones de pago siempre de pago único, nunca suscripción. Permiso para la 7.05 (Python embeddable oficial). |
| 2026-11-14 | Aprobados la propuesta de la 7.05 (AppContainer + escritorio aparte + job; JSON-RPC por entrada y salida estándar) y el prototipo del instalador y del primer arranque guiado (micrófono primero, nombres visibles, etiquetas propias). Python de las extensiones: 3.14.10 (a confirmar). Plan de construcción de la 0.9 (PLAN-0.9 §1b) aprobado; el núcleo pasa a Python 3.14 al empaquetarlo (9.07). |
| 2026-11-15 | Tienda de extensiones en Ajustes **aprobada** (`docs/prototipos/tienda-extensiones.html`). La beta soporta extensiones pero no trae ninguna: las oficiales (OBS, Spotify) se publican y se enseñan desde la 1.0.0. Nada se abre solo al instalar ni al usar Nyx (ni consolas ni la app de Ollama). Datos de uso anónimos: a la base de datos de Tepnyx en Supabase (la del proyecto Decider), en un esquema propio `nyx`, sin otra base de datos de pago. |
| 2026-11-12 | Más adelante: personalidad que se adapta sola a la conversación (con ajustes manuales), Nyx aprende cómo habla el usuario, voz propia entrenada con una persona que ya ha aceptado, soporte en Ayuda y envío real de datos anónimos (HOJA-DE-RUTA). La gestión y documentación de extensiones, prioridad de la 0.7. |

El historial completo de decisiones está en la sección 18 de `docs/SPEC.md`.

## Antes de hacer público el repositorio (fase 6)

Recuérdaselo al usuario al llegar a la fase 6.

- [x] `LICENSE` (GPL-3.0-only en todo) y CLA para contribuciones (`CLA.md`, aceptado por el
  usuario; mejor que lo mire también el abogado) — 2026-11-13
- [x] `SECURITY.md` y `CONTRIBUTING.md` (aceptados, 2026-11-13)
- [x] Revisar todo el historial de git en busca de secretos: ninguno
- [ ] Correo del autor (y usuario de Windows en 5 líneas antiguas) en el historial:
  reescribirlo justo antes de publicar, pendiente de que el usuario lo confirme (`REVISAR.md`)
- [x] Auditoría de licencias de dependencias y modelos: `docs/LICENCIAS.md` (todo compatible;
  `nyx-v1` bajo CC BY-SA 4.0; créditos en la app, en la 0.9)
- [ ] Cambiar la visibilidad en GitHub y configurar SignPath (cuando el usuario diga «publícalo»)
- [x] `whisper-server` recompilado sin `GGML_NATIVE` (con `GGML_BACKEND_DL` y
  `GGML_CPU_ALL_VARIANTS`) el 2026-11-16: `C:\dev\tools\whisper.cpp\build-portable\bin\Release`
  (todas las variantes de CPU y Vulkan). **Las versiones se compilan con
  `-Whisper C:\dev\tools\whisper.cpp\build-portable\bin\Release`**; el de `build\` se cae en
  procesadores sin AVX-512.
- [ ] Subir el cerebro de Nyx a la Release `cerebro-r2`: los trozos de `dist\brain\`
  (`core/scripts/export_brain.py`; el manifiesto con sus huellas ya va en
  `core/nyx/brain/data/cerebro.json`). Sin ellos, el primer arranque baja `qwen2.5:7b`.
- [ ] Las páginas de Nyx y de sus códigos de error (`tepnyx.com/nyx/errores`, desde
  `docs/CODIGOS-DE-ERROR.md`) en la web de Tepnyx: se hacen al final (decisión 2026-11-15).

## Estructura

```text
core/        Núcleo en Python 3.14 (asyncio). Un subpaquete por servicio en core/nyx/
  tests/     Pruebas unitarias y batería de frases
  training/  Entrenamiento del modelo de «Nyx»
ui/          Interfaz Tauri 2 + TypeScript (overlay, ajustes, tema)
installer/   Instalador (Tauri 2 + Svelte): instala con Velopack, oído y voz, y abre Nyx
scripts/     build-release.ps1: núcleo empaquetado + app + Velopack + instalador
docs/        SPEC.md (especificación)
```

## Comandos (núcleo)

Desde `core/`:

```powershell
uv sync
uv run ruff format . ; uv run ruff check .
uv run mypy
uv run pytest
uv run nyx --download-models      # modelos de voz en %LOCALAPPDATA%\Nyx\models (SHA-256)
uv run nyx --ask "¿Qué día es hoy?"   # una pregunta sin interfaz ni micrófono
uv run nyx --demo --print-token   # núcleo suelto, recorre los estados
uv run python scripts/check_ollama.py    # prueba de GPU (ver docs/benchmarks)
uv run python scripts/battery.py        # batería de frases con Ollama (no ejecuta nada)
uv run python scripts/record_samples.py positivos   # grabar «Nyx» (también: parecidas, continuo)
uv run python scripts/wake_eval.py --motor propio    # medir la activación
uv run python scripts/calibrate.py   # calibrar con las grabaciones (solo guarda si mejora)
uv run python training/download.py ; generate.py ; filter.py ; build.py ; train.py   # entrenar
```

## Comandos (interfaz)

Desde `ui/`:

```powershell
npm install
npm run tauri dev        # app completa con el bucle de voz (NYX_DEMO=1: núcleo en modo demo)
npm run check            # svelte-check
npm run format           # prettier
cargo clippy --manifest-path src-tauri/Cargo.toml -- -D warnings
```

## Versión para publicar (desde la raíz)

```powershell
.\scripts\build-release.ps1 -Version 0.9.0 -Whisper C:\ruta\whisper.cpp\build\bin\Release
# → Releases\<versión>\: TepnyxNyx-win-Setup.exe, paquetes de Velopack, SHA256SUMS.txt e «Instalar Nyx.exe»
```

Arquitectura de procesos: `ui/src-tauri` (Rust) es el proceso principal. Lanza el núcleo con `uv run`, le pasa el token en `NYX_TOKEN` y lee el puerto de la línea `ready` en stdout. Las ventanas piden puerto y token con el comando `core_endpoint` y se conectan por WebSocket. El protocolo está duplicado en `core/nyx/bridge/protocol.py` y `ui/src/lib/protocol.ts`: cambia los dos a la vez.

Ajustes en `%APPDATA%\Nyx\settings.json` (micrófono, voz, ruta de `whisper-server.exe`, modelo de Ollama, `responses.speak_typed` para responder también en voz a lo escrito, `appearance.glass` para el motor de cristal); se leen al arrancar el núcleo (bandeja → Reiniciar núcleo). Atajos: `Win+Alt+N` escribir, `Win+Alt+H` hablar, `Win+Alt+,` Ajustes. Las acciones quedan en `%LOCALAPPDATA%\Nyx\actions\AAAA-MM-DD.jsonl`. Cada petición deja su latencia en el registro (`Latencia: fin de frase → voz …`).

Problema conocido en este equipo: la caché de uv está en una carpeta sincronizada con la nube, así que `core/pyproject.toml` usa `link-mode = "copy"`. Si `uv` da "os error 32" o "396", borra `core/.venv` y repite.

Errores vistos al usar Nyx: se apuntan en [docs/ERRORES.md](docs/ERRORES.md) y se corrigen por tandas sin parar el plan.

## Preguntas abiertas

- Ajuste fino de la paleta de grises sobre fondos reales.
- Hoja de ruta de la 0.5 a la 2.0: **aprobada el 2026-11-11** en [docs/HOJA-DE-RUTA.md](docs/HOJA-DE-RUTA.md). Siguiente: plan de la 0.6 (cerebro). Cada versión pasa a la SPEC al empezarla.
- Instalador propio y onda de «Nyx listo»: propuesta del 2026-11-10 en [docs/INSTALADOR-Y-MOTOR-GRAFICO.md](docs/INSTALADOR-Y-MOTOR-GRAFICO.md) (el motor ya está en la SPEC). Pendiente de plan y aprobación.
