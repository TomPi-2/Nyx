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
| 9.09 | **Publicación** (GitHub Actions): etiqueta `v…` → compilar, empaquetar con Velopack, firmar (SignPath) y subir a Releases. | El repositorio público («publícalo») y SignPath |

**Sin el usuario se puede hacer:** 9.01, 9.02 (prototipos), 9.03 y 9.05; preparar 9.04 tras
el visto bueno. Lo demás necesita descargar herramientas (Velopack `vpk`, Python oficial), una
Release publicada o probar en los dos equipos.

## 2. Gestión de extensiones (0.7, tarea 7.11)

La parte del núcleo está hecha (7.01–7.04 y 7.08). La pantalla de Ajustes → Extensiones va
primero como prototipo (`docs/prototipos/extensiones.html`): lista con permisos a la vista,
activar, desinstalar, actualizar, modo desarrollador y la etiqueta «sin revisar».

## 3. Registro

| Tarea | Agente | Commit | Notas para la revisión | Revisado |
| --- | --- | --- | --- | --- |
| 9.01 y 9.02 (prototipo) | Claude | `843cf45` | `docs/prototipos/instalador.html`: bienvenida (Nyx respira), licencia libre explicada en tres líneas (sin «aceptar»), qué se instala con tamaños y espacio libre, instalación con barras líquidas y la forma de Nyx que se llena con el total, corte de red (pausa y sigue donde iba), preparación (cerebro en la gráfica, oído, voz) y final: el panel se recoge en Nyx y sale la onda, que cruza dos monitores de distinto tamaño con el mismo reloj. Alternativas «Nyx aparece y desaparece» y «Nada», y la onda al encender el PC. **Pendiente del visto bueno del usuario.** | |
| 9.03 | Claude | `7938d43` | `appearance.ready_indicator` (onda · nyx · nada; por defecto onda) en el modelo de ajustes, el saludo del puente (protocolo **v18**, los dos lados) y Ajustes → Apariencia («Al estar lista», con la explicación de cada opción); SPEC §13. La onda en sí es la 9.04 (tras el visto bueno del prototipo). pytest 1.707, svelte-check sin errores. | |
| 9.05 | Claude | `aea9f93` y (este commit) | `nyx/update/`: `backup.py` (copia de ajustes, `extensions.json`, cola de la partida, ventana de Ajustes y las bases de alarmas y atajos con la API de copia de SQLite, cerrando las conexiones; restaurar manda los `-wal`/`-shm` viejos a la papelera; se quedan 3 copias y las demás a la papelera), `migrations.py` (versiones número a número; al arrancar, si la versión sube y hay migraciones de ese tramo: copia, las aplica en orden y, si una falla, restaura y no apunta la versión; al bajar no migra; hoy la lista está vacía), `moment.py` (`UpdateGate`: pipeline libre y sin botones pendientes, sin partida ni cola). Ajustes `updates.mode` y `updates.channel` (editables) en Ajustes → General; `main.py` migra antes de leer los ajustes. Encontrado: `with sqlite3.connect()` no cierra la conexión (en Windows la copia no se podía mover). Falta quien pregunte al `UpdateGate`: la app con Velopack (9.06). pytest 1.715. | |
