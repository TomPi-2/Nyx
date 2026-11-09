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
  - CI en GitHub Actions (Windows): ruff, mypy, pytest, prettier, svelte-check, rustfmt y clippy.
- Especificación en `docs/SPEC.md`, con la sección 18 (decisiones tomadas).
- Estructura del repositorio según la sección 16: `core/` (paquete `nyx` con un subpaquete por servicio), `ui/` y `docs/`.
- `CLAUDE.md` con las reglas de trabajo y las decisiones tomadas.

### Cambiado

- Cristal: el Acrylic de Windows queda descartado (se ve sólido en ventanas sin foco y actualiza lo de detrás con unos 2 s de retraso). La isla y las burbujas usan un tinte gris translúcido al 84 % en CSS, que cambia en el mismo fotograma que el fondo (medido: menos de 25 ms, también con Chrome). El cristal con desenfoque real queda para un motor propio más adelante.
- SPEC: sin cuenta de usuario; datos de uso anónimos solo con permiso (sección 8); interfaz en ventanas flotantes propias en lugar de capa a pantalla completa, con elección de monitor según ajustes y modo partida (secciones 9 y 11); Svelte 5 y `uv` en el stack (sección 2); repositorio público desde la fase 6 (sección 15).
