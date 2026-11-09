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

Fase actual: **1 — Base y pruebas técnicas** (sin empezar). El repositorio solo tiene la estructura de carpetas.

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
ruff format . ; ruff check .
mypy
pytest
```

## Preguntas abiertas

- Ajuste fino de la paleta de grises sobre fondos reales.
- Modelo de LLM final tras la batería de pruebas (7–8B frente a 14B).
- Viabilidad del Acrylic con esquinas muy redondeadas (prueba de la fase 1).
- Ubicación fija para el tiempo (ciudad).
