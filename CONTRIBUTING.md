# Cómo contribuir a Nyx

¡Gracias por querer ayudar! Nyx es un asistente de voz y texto para Windows, gratis, local y de
código abierto (GPL-3.0). Antes de empezar, lee la especificación: [docs/SPEC.md](docs/SPEC.md).

## Antes de nada

- **Acuerdo de contribución (CLA):** para aceptar tu código tienes que firmar el
  [CLA](CLA.md) una vez. Nos permite mantener y, si hiciera falta, cambiar la licencia del
  proyecto; tú sigues siendo el autor de lo que aportas.
- **Fallos de seguridad:** no los publiques; sigue [SECURITY.md](SECURITY.md).
- **Ideas grandes:** abre primero una incidencia para hablarlo. Así no trabajas en algo que
  no encaja con el plan ([docs/HOJA-DE-RUTA.md](docs/HOJA-DE-RUTA.md)).

## Reglas que no cambian

- **Solo Windows 11.** Nada que dependa de CUDA: la gráfica de referencia es AMD (Vulkan).
- **Gratis y local.** Nada de servicios de pago ni librerías con licencias que lo impidan.
- **Seguridad (SPEC sección 8):** nunca se baja el nivel de riesgo de una acción ni se borra
  de forma permanente (siempre a la papelera). El nivel lo decide SafetyGuard, no el modelo.
- **Cada herramienta** va en su propio archivo, con su esquema tipado, su nivel de riesgo, su
  política en partida y sus pruebas.
- **La interfaz** sigue la sección 12 de la SPEC: grises, translúcida, redondeada, sin bordes.
- Código tipado y con formato automático; comentarios en español donde aporten.

## Preparar el entorno

Núcleo (Python 3.12 con [uv](https://docs.astral.sh/uv/)), desde `core/`:

```powershell
uv sync
uv run nyx --download-models
```

Interfaz (Tauri 2 + Svelte 5), desde `ui/`:

```powershell
npm install
npm run tauri dev
```

Necesitas [Ollama](https://ollama.com) con `qwen2.5:7b` para el cerebro.

## Comprobaciones antes de enviar

Desde `core/`:

```powershell
uv run ruff format . ; uv run ruff check .
uv run mypy
uv run pytest
```

Desde `ui/`:

```powershell
npm run format
npm run check
cargo clippy --manifest-path src-tauri/Cargo.toml -- -D warnings
```

Si tocas las reglas del router (`core/nyx/brain/router/`), añade pruebas con frases que deben
activarla **y con frases parecidas que no**, y comprueba que no cambia nada más. Si tocas el
cerebro, pasa la batería: `uv run python scripts/battery.py` (necesita Ollama).

## Commits y peticiones de cambio

- Un cambio por petición, con su prueba.
- Mensajes de commit en español, en presente y con la tarea si la hay («6.28: …»).
- Actualiza `CHANGELOG.md` y, si cambia el comportamiento, la SPEC.
- El protocolo entre núcleo e interfaz está duplicado (`core/nyx/bridge/protocol.py` y
  `ui/src/lib/protocol.ts`): cámbialos a la vez y sube `PROTOCOL_VERSION`.

## Qué no se acepta

- La voz propia de Nyx y sus grabaciones no son libres: no las incluyas, extraigas ni uses
  fuera del proyecto (ver [docs/LICENCIAS.md](docs/LICENCIAS.md)).
- Código copiado de proyectos con licencias incompatibles con GPL-3.0.
