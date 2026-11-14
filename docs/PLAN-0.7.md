# Plan de la versión 0.7 — Extensiones

> **Aprobado por el usuario el 2026-11-13.** Se empieza al cerrar la 0.6. Fuente:
> [HOJA-DE-RUTA.md](HOJA-DE-RUTA.md) §2 (0.7), §4 (plataforma de extensiones) y §5 (modos).
> Funciona como [PLAN-0.6.md](PLAN-0.6.md): una tarea por sesión, sus comprobaciones (§0.3 de
> ese plan, que siguen valiendo), un commit y su fila en el Registro. Si algo choca con la
> SPEC o con `CLAUDE.md`, manda la SPEC y se pregunta.

**Objetivo de la 0.7:** dejar preparado que, desde la 1.0, se instalen extensiones sin
actualizar Nyx, sin que ninguna pueda saltarse la seguridad (SPEC §8) ni tocar un juego, y con
una documentación tan buena que alguien de fuera pueda hacer una sin ayuda. Además, la base de
los modos (Partida, Trabajo, Noche y Privacidad).

**Para cerrar la 0.7** (HOJA-DE-RUTA §2): las tres extensiones de ejemplo se instalan,
actualizan y desinstalan sin reiniciar Nyx; una extensión que se cuelga o intenta algo sin
permiso no afecta a Nyx (pruebas automáticas); alguien que no sea Claude ni el usuario hace una
con la documentación. Y lo de siempre: la batería del cerebro no baja y el coste en partida
sigue dentro del objetivo (SPEC §14).

---

## 0. Reglas propias de la 0.7

Además de las de la 0.6 (§0.2 de su plan):

- **Ninguna extensión toca Windows directamente.** Todo lo pide a Nyx por su API, y Nyx lo
  pasa por los permisos aceptados, `SafetyGuard` (con el riesgo mínimo del permiso, aunque la
  extensión declare menos) y el modo partida.
- **No existe ningún permiso para un juego**: ni teclas, ni leer su pantalla o su memoria, ni
  inyectarse. La API no tiene la forma de hacerlo.
- **Lo que trae una extensión es contenido de fuera:** sus descripciones, su conocimiento y lo
  que devuelven sus herramientas llegan al modelo marcados como externos (`ToolResult.external`),
  igual que una web.
- **Instalar no ejecuta nada.** El código de una extensión solo corre en su proceso aislado y
  después de aceptar sus permisos.
- **SDK, plantilla, ejemplos y documentación con licencia MIT** (decisión del 2026-11-11); el
  núcleo sigue GPL-3.0.

## 1. Orden y dependencias

```text
A. Base               7.01 → 7.02 → 7.03 → 7.04
B. Código aislado     7.05 (DECISIÓN) → 7.06 → 7.07          (tras A)
C. Firma              7.08 (DECISIÓN)                        (tras 7.02)
D. Formas y modos     7.09 · 7.10 (DECISIÓN en una parte)    (tras 7.03)
E. Interfaz           7.11                                   (tras 7.02; prototipo antes)
F. SDK y documentos   7.12 → 7.13 → 7.14                     (tras 7.07)
G. Cerebro            7.15 · 7.16                            (independientes)
H. Cierre             7.17
```

Recomendación: **Claude** hace A, B, C y la revisión de todo lo demás (seguridad y
arquitectura); D, E, G y los ejemplos los puede hacer cualquiera con el diseño fijado.

## 2. Bloque A — Base (sin código de terceros)

### 7.01 Paquete `.nyxext` y manifiesto · Claude

`core/nyx/ext/manifest.py`: el manifiesto de HOJA-DE-RUTA §4.2 como modelo pydantic estricto
(id `autor.nombre`, versión SemVer, `nyx_api`, tipos, permisos con su forma exacta
—`net:<host>:<puerto>`, `files:read:<carpeta conocida>`…—, política en partida por
herramienta y licencia). Nyx empieza su API en `1.0`. Lo que no valide no se instala.
**Pruebas:** manifiestos buenos y malos (permiso inventado, id raro, versión de API que no
casa, campos de más).

### 7.02 Instalar, actualizar, desactivar y desinstalar · Claude

`core/nyx/ext/store.py`: extensiones en `%LOCALAPPDATA%\Nyx\extensions\<id>\<versión>\`.
- Abrir el zip con cuidado: sin rutas que salgan de su carpeta, sin enlaces, tamaño y número
  de archivos máximos (un zip bomba no tumba a Nyx).
- Cambio de versión atómico (la nueva se prepara aparte y se cambia de golpe; si falla, sigue
  la anterior). Desinstalar manda la carpeta a la papelera, como todo en Nyx.
- Estado en `%APPDATA%\Nyx\extensions.json` (activas, permisos aceptados, versión).
- Si una actualización pide más permisos, no se activa hasta que se acepten.

**Pruebas:** zip con `..\`, zip enorme, actualización que falla a medias, desinstalar y volver
a instalar.

### 7.03 Tipos sin código · cualquiera

Cargadores validados para acciones por app, preajustes, conocimiento y personalidad
(HOJA-DE-RUTA §4.3). **El catálogo actual de `app_action` (`tools/app_catalog.py`) pasa a ser
una extensión integrada en JSON**, la primera prueba de que el formato sirve. Los preajustes
solo tocan los ajustes editables (nunca los niveles de seguridad).

### 7.04 Herramientas y grupos en caliente · Claude

El registro y el selector (`tools/registry.py`, `brain/select.py`, `tools/groups.py`) aceptan
herramientas y grupos que llegan y se van sin reiniciar. Cada extensión declara sus grupos y
palabras clave. Ojo: cambiar las herramientas cambia el prefijo del modelo y su caché, así que
se recalienta al instalar o desinstalar, nunca en partida.

## 3. Bloque B — Código de las extensiones, aislado

### 7.05 Cómo se aísla · DECISIÓN (Claude)

Probar y proponer, con medidas, antes de construir:
1. **Proceso con token de baja integridad o AppContainer** (HOJA-DE-RUTA §4.4): cuál impide de
   verdad leer los archivos del usuario y abrir la red por su cuenta, y cuál deja funcionar a
   Python.
2. **El Python de las extensiones**: el «embeddable» oficial de Python (licencia PSF) dentro de
   Nyx, con las dependencias de cada extensión dentro de su paquete (sin `pip` al instalar).
3. Límites con un objeto de trabajo (`winjob.py`): CPU, memoria y prioridad mínima en partida.

Se para y se pregunta al usuario con lo medido.

### 7.06 Host de extensiones · Claude

`core/nyx/ext/host.py`: un proceso por extensión con código, hablando con Nyx por una tubería
con nombre (JSON-RPC). Si se cae, se reinicia; tres caídas seguidas, se desactiva y se avisa.
Tiempo máximo por llamada (como `Tool.timeout_s`).

### 7.07 API y permisos · Claude

Lo que una extensión puede pedir (HOJA-DE-RUTA §4.5) y cómo lo comprueba Nyx: cada petición
pasa por el permiso aceptado y por `SafetyGuard`. Las herramientas de una extensión se ven en
Nyx como `Tool` normales (riesgo, política en partida, confirmación, deshacer). `secrets`, en
el Administrador de credenciales de Windows. **Pruebas automáticas:** una extensión que pide
red sin permiso, que lee un archivo fuera de su permiso, que se cuelga, que devuelve basura,
que intenta mandar teclas: Nyx sigue igual y lo apunta.

## 4. Bloque C — Firma

### 7.08 Firma, revocación y modo desarrollador · DECISIÓN (Claude)

Firma Ed25519 (con `cryptography`, Apache-2.0 o BSD: compatible), lista de revocación firmada
que se descarga cada día y modo desarrollador (cargar una carpeta sin firmar, con la etiqueta
«sin revisar» bien visible). **A decidir:** dónde vive la clave privada de Tepnyx y quién
firma mientras no haya portal (propuesta: un script que firma a mano en el PC del usuario, con
la clave fuera del repositorio, como la de las actualizaciones).

## 5. Bloque D — Formas y modos

### 7.09 Formas de Nyx · cualquiera (diseño de Claude)

El contrato de HOJA-DE-RUTA §4.3: uniforms fijos (estado, nivel de audio, fase, color,
tamaño, tiempo) y caja máxima, para respetar el hueco de 14 px. La forma actual pasa a ser
`tepnyx.forma-nyx`, la predeterminada (`ui/src/overlay/shape/`). Una forma se dibuja sin red
ni acceso a nada.

### 7.10 Modos · cualquiera (diseño de Claude) · DECISIÓN en una parte

Sistema de modos (HOJA-DE-RUTA §5): disparadores, acciones al entrar y al salir (que se
deshacen al salir), comportamiento de Nyx y políticas de herramientas. **El modo partida
actual (`game/`, `gamemode/`) se convierte en el primer modo** sin cambiar cómo funciona; luego
Trabajo, Noche y Privacidad. **A decidir:** Windows no tiene API pública para la luz nocturna
ni para «no molestar»; se prueban las formas no oficiales y, si no son fiables, el modo abre
la página de Configuración.

## 6. Bloque E — Interfaz

### 7.11 Ajustes → Extensiones y Modos · cualquiera

Prototipo HTML antes (como en la 6.28) y el visto bueno del usuario. Lista con permisos a la
vista, activar, desinstalar, actualizar, modo desarrollador; y los modos. SPEC §12 al pie de
la letra.

## 7. Bloque F — SDK y documentación (prioridad del usuario, 2026-11-12)

### 7.12 `nyx-sdk` y `nyx-ext` · Claude

Paquete Python (MIT) con los tipos, el decorador de herramientas, el cliente de la API y un
Nyx falso para probar; línea de órdenes `nyx-ext new / validate / pack / run`.

### 7.13 Documentación para desarrolladores · cualquiera (revisa Claude)

Cómo empezar, referencia de la API y del manifiesto, permisos, buenas prácticas
(descripciones cortas para el modelo, grupos y palabras clave: `tools/groups.py` y
`docs/benchmarks/grupos-6.20b.md`), pruebas y publicación. Tres ejemplos: una herramienta, una
forma y un modo.

### 7.14 Extensiones oficiales de prueba · cualquiera

OBS básico (grabar, directo, escena; por obs-websocket, sin teclas) y Spotify «poner algo
concreto». **A comprobar antes:** la licencia de la librería de obs-websocket que se use, y si
Spotify deja hacerlo sin cuenta de desarrollador (si no, que Nyx lo diga y ofrezca guiar,
decisión del 2026-11-11).

## 8. Bloque G — Cerebro (lo que pasó de la 0.6)

### 7.15 Índice de grupos de último recurso (antes 6.20c) · Claude

Con muchas extensiones no caben todas las herramientas: si el selector no sabe qué grupo es,
el modelo elige en un índice de una línea por grupo. Se mide con la batería y con grupos de
extensiones falsas.

### 7.16 Recordar planes que han funcionado (resto de la 6.07) · Claude

Como los atajos aprendidos (`brain/shortcuts.py`), pero para planes de varios pasos que el
usuario ha aprobado: la próxima vez, sin pasar por el modelo y con los mismos niveles de
riesgo. Nunca se aprende en partida ni un paso rojo sin confirmar.

## 9. Bloque H — Cierre

### 7.17 Cierre de la 0.7 · Claude

Revisión de todo, las pruebas de «para cerrar», batería y coste en partida, SPEC (sección
nueva de extensiones y modos), `CHANGELOG.md` y `CLAUDE.md` (siguiente: 0.8).

## 10. Fuera de la 0.7

- Web de extensiones, portal de desarrolladores y extensiones de pago: 1.0 y siguientes.
- Widgets del Overlay y el resto de modos (Streaming, Relax): 1.1.
- Personalidad que se adapta sola, aprender cómo habla el usuario, envío real de datos
  anónimos y soporte en Ayuda: según la hoja de ruta (pedidos el 2026-11-12).

## 11. Registro

| Tarea | Agente | Commit | Notas para la revisión | Revisado |
| --- | --- | --- | --- | --- |
| 7.01 | Claude | `468092a` | `nyx/ext/manifest.py`: manifiesto estricto (pydantic, `extra=forbid`, JSON validado tal cual). Id `autor.nombre`, SemVer de cualquier número de cifras, rango `nyx_api` (API 1.0), tipos sin repetir (sin `widget`: 1.1), permisos con su forma exacta y su riesgo mínimo (`files:` solo carpetas conocidas por nombre, nunca rutas; `ui:widget` y `screen` se rechazan diciendo cuándo llegan), `game_policy` y `groups` solo con herramientas, licencia (`paid` necesita producto), `homepage` solo https. Sin código no hay permisos. pytest 37 nuevas. | |
| 7.02 | Claude | `7d69235`, `70a63d0` | `nyx/ext/store.py`: el zip se revisa entero antes de extraer (cifrado, enlaces, `..`, rutas absolutas o con unidad, nombres reservados de Windows, `:` de flujos alternativos, puntos o espacios al final, repetidos sin distinguir mayúsculas, 2.000 archivos, 128 MB por archivo y 256 MB en total, ratio 200:1) y al extraer se cuentan los bytes de verdad. Se extrae en una carpeta aparte y se cambia con `os.replace`; el estado (`extensions.json`) se escribe aparte y se sustituye. Una actualización con permisos nuevos queda «pendiente» y la anterior sigue activa hasta aceptar. Sin bajar de versión. Desinstalar y las versiones viejas, a la papelera. `extensions.json` dañado: se ignora con copia. pytest 27 nuevas. | |
| 7.03 | Claude | `d3f4241` | `nyx/ext/content.py`: acciones por app (teclas por el analizador de Nyx y su lista de bloqueo; nunca en ejecutables de Nyx; `*` o `en` obligatorio), preajustes (solo `PRESET_KEYS`: apariencia, voz, tono, seguimiento, sensibilidad y modo partida; nunca políticas, privacidad, red, cerebro ni la palabra; valores validados con `Settings`), conocimiento (Markdown por `##`, 40 archivos de 64 KB) y personalidad (tono y frases en texto llano, sin código ni enlaces). Un archivo malo se anota en `problems` y no tumba el resto. **El catálogo de `app_action` es la extensión integrada `nyx/ext/builtin/tepnyx.apps`** (mismos 9 perfiles y 36 acciones); `set_extension_profiles` añade las de extensiones y `app_action` valida contra todas. Pendiente para 7.04: cargar las extensiones instaladas en marcha (y el conocimiento como externo en `nyx_info`). pytest 1.689. | |
| 7.04 | Claude | `2c003c2` | `ToolRegistry` con dueño por herramienta (`register(owner=)`, `unregister_owner`, `version`); `nyx/ext/manager.py` (`ExtensionManager`): al instalar, actualizar, activar, desactivar o desinstalar relee las activas y aplica acciones (`set_extension_profiles`), conocimiento (en `nyx_info`, como **externo** y sin tapar lo de Nyx), herramientas (de `tool_factory`, que pondrá el host de 7.06/7.07) y grupos (nombre propio si choca con uno de Nyx; palabras clave normalizadas y escapadas; tope de tamaño), y crea un selector nuevo que `services` aplica recalentando el modelo. **En partida no cambia nada**: espera a `GameStateChanged(active=False)`. Una extensión rota o con nombres de otra herramienta se apunta en `problems` sin tocar lo demás. `app_action.schema()` lista también las acciones de extensiones (sin extensiones, idéntico: 27.018 caracteres). Al arrancar solo se recarga si hay alguna instalada. pytest 1.698. | |
| 7.05 | Claude | — | **Sin medir: bloqueado.** El prototipo necesitaba descargar el Python «embeddable» oficial (python.org) y ejecutarlo aislado (token de baja integridad frente a AppContainer); el modo automático no deja descargar y ejecutar un binario de internet sin permiso del usuario. Lo que dice la documentación de Windows (a comprobar): la baja integridad **no** impide leer los archivos del usuario ni abrir la red (solo escribir hacia arriba); AppContainer sí impide las dos cosas, pero la carpeta del Python y la tubería con Nyx tienen que dar permiso al SID del contenedor. Propuesta: AppContainer sin capacidades de red (la red, por Nyx con `net:`). Pendiente de que el usuario lo permita (`REVISAR.md`). | |
| 7.08 | Claude | `d25cd94` | **Decidido por Claude (a confirmar):** firma Ed25519 (`cryptography`, Apache-2.0/BSD) sobre el SHA-256 de cada archivo y su ruta (todo menos `signature`); claves públicas de Tepnyx por id dentro de Nyx (`TRUSTED_KEYS`, vacío hasta que el usuario cree la suya); la privada en `%APPDATA%\Tepnyx\keys\` del equipo que firma, con `scripts/sign_extension.py` (`--nueva-clave` nunca sobrescribe; firma paquetes tras revisarlos como Nyx y la lista de revocación). Sin firma válida, solo en modo desarrollador («sin revisar», `dev`). Lista de revocación firmada con número de serie (nunca se acepta una más vieja), una vez al día y solo con alguna extensión firmada instalada; sin red vale la guardada; las retiradas no se cargan y Ajustes dice por qué. pytest 1.707. | |
| 7.11 (prototipo) | Claude | `6ded7c8` | `docs/prototipos/extensiones.html`: Ajustes → Extensiones con las instaladas (permisos en lenguaje normal, activar, desinstalar a la papelera con confirmación), una actualización que pide un permiso nuevo (sigue la anterior hasta aceptarlo), una retirada por Tepnyx (bloqueada, con el motivo), una solo de acciones («no pide nada, no ejecuta código»), instalar desde archivo (firmada por Tepnyx o «Sin revisar»), la tienda «pronto» y el modo desarrollador (cargar carpeta). Los modos van aparte, con la 7.10. **Pendiente del visto bueno del usuario.** | |
| 7.11 (núcleo) | Claude | `933afb9` | Lo que usará la pantalla, sin tocar la interfaz visible: `nyx/ext/service.py` (`ExtensionsService`) atiende `ExtRequested` (listar, inspeccionar un `.nyxext` sin instalar ni ejecutar nada —nombre, autor, permisos, si lo firma Tepnyx, si se puede instalar—, instalar tras ver los permisos, aceptar, activar, desactivar, desinstalar) y contesta siempre con el estado completo. Sin firma solo con `extensions.dev_mode` (ajuste editable nuevo). Protocolo v18: `ext` y `extensions` en los dos lados (`protocol.py`, `protocol.ts`). pytest 1.719, svelte-check sin errores. | |
| 7.16 | Claude | `2b8dc58` | `brain/shortcuts.py`: tabla `plans` en la misma base que los atajos; `learn_plan` guarda planes de 2 a 4 pasos con las reglas de un atajo en cada paso (nada rojo, nada de `NEVER`, nada que dependa del momento; las esperas se quitan y las vuelve a poner `with_waits`). El pipeline aprende si el LLM resolvió la frase en una sola vuelta (sin bucle de agente: si consultó algo, no se aprende), todos los pasos salieron bien, ninguno se dejó para después y no hay partida; lo repite antes del LLM («Plan aprendido»), pasando cada paso por el ejecutor (mismos riesgos y confirmaciones). Deshacer justo después lo olvida; «Olvidar» y «Olvidar todos» también borran planes. Pendiente: enseñarlos en Ajustes → Cerebro junto a los atajos. pytest 1.720. | |
| 7.09 (diseño y núcleo) | Claude | `22d71ad`, `2479d0a` | Contrato en `docs/extensiones/formas.md`: shader GLSL ES 1.00 (bucles con límite fijo: no puede colgar la gráfica) con uniforms fijos `nyx_resolution`, `nyx_size`, `nyx_time`, `nyx_state` (0–6), `nyx_audio`, `nyx_phase`, `nyx_appear`, `nyx_color`; alfa premultiplicado; caja máxima `box` de 0,5 a 1,25 veces el tamaño (los 14 px con los paneles se cuentan desde ella); sin texturas, sin uniforms propios, sin `#version`/`#extension`; coste medido al cargar. Núcleo: `content.py` carga `shape/shape.json` y `shape/shape.glsl` (32 KB) y rechaza lo prohibido sin contar los comentarios. Falta (cualquiera, con la interfaz delante): dibujarla en la isla con el preámbulo, volver a la de siempre si no compila, medir y registrar la forma actual como `tepnyx.forma-nyx`. pytest +11. | |
| 7.10 (decisión) | Claude | `cc2f225` | **Luz nocturna y «No molestar», decidido por Claude (a confirmar):** en la 0.7 no se usan las formas no oficiales (el blob de `CloudStore\…luelightreduction` y el estado WNF de las notificaciones): escriben en zonas sin documentar que Windows cambia sin avisar, y probarlas exigía tocar la configuración del usuario sin él delante. El modo Noche abre la página exacta (`ms-settings:nightlight`, `ms-settings:notifications`, que Nyx ya conoce) y Nyx dice qué tocar («Te abro la luz nocturna: actívala arriba»). Se puede reconsiderar con una extensión «sin revisar» que el usuario instale a sabiendas. El sistema de modos en sí (disparadores, acciones que se deshacen al salir, partida como primer modo) queda por hacer: cambia cómo funciona el modo partida y hay que probarlo jugando. | |
| 7.12 (adelanto) | Claude | (este commit) | `core/scripts/nyx_ext.py`: `new` (ejemplo de cada tipo sin código: knowledge, actions, preset, personality, shape; nunca sobrescribe), `validate` (manifiesto y contenido como al instalar) y `pack` (solo si valida; se comprueba el paquete con `read_package`). Probado con los cinco tipos. **Falta y se pregunta al usuario:** el SDK con licencia MIT (decisión 2026-11-11) tendría que llevar la validación, que hoy está en el núcleo (GPL); como autor puede publicar esos módulos también con MIT. Y las extensiones con código esperan al host (7.05–7.07). | |
