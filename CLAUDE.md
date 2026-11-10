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
- La interfaz sigue la sección 12 al pie de la letra: solo grises, translúcida, todo redondeado y sin bordes. La personalización queda para la fase 7.
- Mantén [CHANGELOG.md](CHANGELOG.md) y actualiza `docs/SPEC.md` si acordamos cambios.

## Estado

Fase actual: **4 — «Nyx» de verdad**: 4a (medir), 4b (entrenar) y 4c (integrar) hechos; falta 4d (calibración con muestras del usuario, registro de activaciones, palabras personalizadas, verificación de voz opcional). Fases 1 y 2 cerradas el 2026-11-09; fase 3 cerrada el 2026-11-10.

## Decisiones tomadas

| Fecha | Decisión |
| --- | --- |
| 2026-11-09 | Nyx será gratis y de código abierto (GPL-3.0 + CLA). El repositorio sigue privado hasta la fase 6. |
| 2026-11-09 | Dos equipos: PC con RX 7700 XT (principal y de referencia) y portátil con RTX 3070 Laptop. Las pruebas de rendimiento se hacen en ambos para fijar los requisitos mínimos. Todo por Vulkan, nada de CUDA. |
| 2026-11-09 | La app Tauri es el proceso principal (bandeja, instancia única) y lanza el núcleo Python como proceso hijo; lo reinicia si se cae. |
| 2026-11-09 | Interfaz: Svelte 5 + TypeScript para la UI y WebGL/Canvas directo para el orbe. |
| 2026-11-09 | Python gestionado con `uv` (Python 3.12). |
| 2026-11-09 | Sin cuenta. Datos de uso anónimos solo con permiso (SPEC sección 8). |
| 2026-11-09 | Interfaz en ventanas flotantes propias, ocultas en reposo; el monitor se elige según ajustes y modo partida (SPEC sección 11). |
| 2026-11-09 | LLM provisional `qwen2.5:7b`; Whisper large-v3-turbo q5 con Vulkan (0,17 s por frase). Falta la prueba del portátil para los requisitos mínimos. |

El historial completo de decisiones está en la sección 18 de `docs/SPEC.md`.

## Antes de hacer público el repositorio (fase 6)

Recuérdaselo al usuario al llegar a la fase 6.

- [ ] `LICENSE` (GPL-3.0) y CLA para contribuciones
- [ ] `SECURITY.md` y `CONTRIBUTING.md`
- [ ] Revisar todo el historial de git en busca de secretos
- [ ] Auditoría de licencias de dependencias y modelos (sección 2)
- [ ] Cambiar la visibilidad en GitHub y configurar SignPath

## Estructura

```text
core/        Núcleo en Python 3.12 (asyncio). Un subpaquete por servicio en core/nyx/
  tests/     Pruebas unitarias y batería de frases
  training/  Entrenamiento del modelo de «Nyx»
ui/          Interfaz Tauri 2 + TypeScript (overlay, ajustes, tema)
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

Arquitectura de procesos: `ui/src-tauri` (Rust) es el proceso principal. Lanza el núcleo con `uv run`, le pasa el token en `NYX_TOKEN` y lee el puerto de la línea `ready` en stdout. Las ventanas piden puerto y token con el comando `core_endpoint` y se conectan por WebSocket. El protocolo está duplicado en `core/nyx/bridge/protocol.py` y `ui/src/lib/protocol.ts`: cambia los dos a la vez.

Ajustes en `%APPDATA%\Nyx\settings.json` (micrófono, voz, ruta de `whisper-server.exe`, modelo de Ollama, `responses.speak_typed` para responder también en voz a lo escrito); se leen al arrancar el núcleo (bandeja → Reiniciar núcleo). Atajos: `Win+Alt+N` escribir, `Win+Alt+H` hablar. Las acciones quedan en `%LOCALAPPDATA%\Nyx\actions\AAAA-MM-DD.jsonl`. Cada petición deja su latencia en el registro (`Latencia: fin de frase → voz …`).

Problema conocido en este equipo: la caché de uv está en una carpeta sincronizada con la nube, así que `core/pyproject.toml` usa `link-mode = "copy"`. Si `uv` da "os error 32" o "396", borra `core/.venv` y repite.

## Preguntas abiertas

- Ajuste fino de la paleta de grises sobre fondos reales.
- Modelo de LLM final tras la batería de pruebas (provisional: `qwen2.5:7b`).
- Requisitos mínimos: faltan las pruebas del portátil (RTX 3070 Laptop).
- Ubicación fija para el tiempo (ciudad).
