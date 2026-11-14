# Hoja de ruta de Nyx: de la 0.5 a la 2.0

> Propuesta del 2026-11-11, **aprobada por el usuario el mismo día** con las decisiones de la sección 7. La SPEC (secciones 1, 13, 14, 16 y 18) se actualiza al empezar cada versión con lo que le toque; hasta entonces, la SPEC sigue mandando en lo que ya está hecho. Requisitos del sistema medidos en los dos equipos: [benchmarks/requisitos.md](benchmarks/requisitos.md).

Este documento reúne en un solo plan lo que queda de las fases 5 a 7, los fallos vistos al probar Nyx con Rocket League (2026-11-11), las ideas nuevas (Vision, Overlay, Extensiones, Modos, IA, productividad y seguridad) y cómo ganar dinero sin que el uso normal deje de ser gratis. Para cada cosa dice en qué versión entra y por qué ahí.

## 0. Resumen

| Versión | Nombre | Qué trae | Fase |
| --- | --- | --- | --- |
| **0.5** ✓ | Partida e interfaz (cerrada el 2026-11-11) | Cierre de la fase 5 + **correcciones urgentes del modo partida** (lag, comandos leídos en voz alta, cola diferida) | 5 |
| **0.6** | Cerebro | Nyx entiende mucho mejor y hace mucho más: bucle de agente, búsqueda en internet, aprender procedimientos, resto de herramientas, batería de 300+ frases, modelo final | 6a |
| **0.7** | Extensiones | **Plataforma de extensiones (API 1.0)**, SDK, documentación, firma y revisión. Formas de Nyx como extensión. Modos (base) | 6b |
| **0.8** | Organización y seguridad | Notas, listas, tareas, dictado, resúmenes, calendario local, bloquear el PC, modo privacidad, quién usa micro y cámara | 6c |
| **0.9** | Beta pública | Instalador que deja listos el cerebro, Whisper y la voz; **primer arranque como conversación con Nyx**; actualizaciones, arranque con Windows, cortes de luz, datos anónimos, repositorio público | 6d |
| **1.0** | Lanzamiento | Versión estable, web de extensiones en tepnyx.com, primeras extensiones oficiales gratuitas | — |
| **1.1** | Personalización y streaming | Fase 7 (formas, ubicaciones), Nyx Overlay, modos Streaming y Relax, primeras extensiones de pago (OBS Pro, Rendimiento en juegos) | 7 |
| **1.2** | Vision | Nyx entiende la pantalla con permiso (nunca en juegos), asistente contextual avanzado | 8 |
| **1.3** | Privacidad avanzada | Programas desconocidos, inicio con Windows, privacidad en directo, calendarios externos | 9 |
| **2.0** | Ecosistema | Nyx Plus (nube opcional de pago), extensiones de pago de terceros, verificación de voz, más idiomas | 10 |

Las versiones 0.x son privadas (solo los dos equipos de prueba) hasta la 0.9. El orden importa: **primero que Nyx funcione muy bien (0.5–0.6), después abrirlo a otros (0.7) y solo entonces publicarlo (0.9–1.0)**. Una tienda de extensiones sobre un asistente que no entiende bien no sirve de nada.

## 1. Lo que salió en la prueba con Rocket League

Datos sacados del registro (`%LOCALAPPDATA%\Nyx\logs\core.log` y `actions\2026-11-11.jsonl`). Todo esto entra en la **0.5**, salvo lo marcado como 0.6.

### 1.1 El juego va a tirones cuando Nyx piensa (crítico)

**Causa:** el cerebro estaba en `qwen2.5:14b`. Ese modelo ocupa unos 9 GB de VRAM, Whisper otro ~0,6 GB y Rocket League 2–3 GB: más de los 12 GB de la RX 7700 XT. En el mínimo (8 GB, el portátil) es aún más justo: con el 7B y Whisper quedan unos 2,4 GB para el juego ([requisitos](benchmarks/requisitos.md)). Al pasarse, el controlador mueve memoria entre la VRAM y la RAM y el juego se para. Además, aunque quepa, mientras el LLM genera usa la GPU al 100 % durante 1–10 s y le quita tiempo al juego. Las latencias de esa partida lo confirman: entre 2 y 19 s hasta la voz, frente a 0,8–1 s fuera de ella.

**Qué hacer:**

1. **Presupuesto de VRAM en partida.** Al empezar una partida, Nyx lee la VRAM libre (DXGI `QueryVideoMemoryInfo`). Si el cerebro no cabe con margen (≥ 1,5 GB libres para el juego), lo descarga y usa el **cerebro de partida**.
2. **Cerebro de partida** (ajuste nuevo en Modo partida, «Automático» por defecto): un modelo pequeño en la GPU si cabe o el 7B en la CPU si no. Lo frecuente en partida (música, volumen, hora, alarmas) ya lo resuelve el router sin LLM, así que el LLM solo entra en preguntas.
3. **Nunca el 14B en partida.** Resuelto de raíz el 2026-11-11: el 14B sale de la primera versión (sección 1.2).
4. **La forma de Nyx a 30 fps en partida** (hoy 60) y el cristal ya en Bajo.
5. **Medirlo de verdad:** PresentMon (licencia MIT, de Intel; lee los tiempos de fotograma por ETW sin tocar el juego) con y sin Nyx pensando. Objetivo nuevo para la sección 14: **menos de un 2 % de FPS medios y ningún tirón (fotograma > 2× la media) mientras Nyx piensa o habla**. Se prueba en los dos equipos.
6. A investigar: bajar la prioridad de GPU de Ollama y whisper-server (prioridad de planificación de GPU de Windows). Si funciona, mejor que cambiar de modelo.

### 1.2 El 14B responde mejor pero tarda más

**Decisión del 2026-11-11: fuera de la primera versión.** En la batería de frases acertaba lo mismo (100 %) pero tardaba 8 veces más (4,4 s de mediana frente a 0,55 s), no cabe en tarjetas de 8 GB y junto a un juego da tirones; y cambiar de modelo al entrar y salir de las partidas era frágil (con Alt+Tab, el 14B se quedaba unos segundos junto al juego). Lo que aportaba (respuestas más completas) llega con la búsqueda en internet (0.6), más código alrededor del 7B (0.6) y la nube opcional (2.0). Lo que sigue es el análisis original.

Es lo esperado: tiene el doble de parámetros (≈ 40 tokens/s frente a 77 en la RX 7700 XT). No se arregla eligiendo uno, sino con **dos niveles de cerebro** (0.6, ver sección 3): el rápido decide y responde lo corto, y el grande solo entra cuando hace falta pensar («explícame…», «compara…», o si el usuario dice «piénsalo bien»). Además, la 0.6 prueba modelos más nuevos con licencia Apache 2.0 o MIT (por ejemplo la familia Qwen3, que tiene 4B, 8B y 14B y modo de razonamiento opcional) con la batería de frases.

### 1.3 La cola de «te lo hago al terminar» solo hizo la última

El registro dice otra cosa: **se ejecutaron las dos**, pero la primera era basura. «Muéstrame los FPS en el Rocket League» la cogió la regla `focus` del router como «trae al frente la ventana *los fps en el rocket league*», se dejó para después y al terminar falló («No veo ninguna ventana…»). La burbuja final lo decía en letra pequeña y no se vio.

**Qué hacer:**

1. Comprobar **antes de diferir** que la acción tiene sentido (que la app o ventana existe en la caché). Si no, decirlo al momento.
2. El router no acepta «muéstrame X» como `focus_window` si X no se parece a ninguna ventana o app: pasa al LLM.
3. **Ver y cancelar la cola:** «¿qué tienes pendiente?», «olvida lo de los ajustes».
4. Al terminar la partida, un resumen claro: qué se hizo y qué no, en voz si se hizo algo por voz.
5. La cola se guarda en disco (sobrevive a un reinicio o un corte de luz).

### 1.4 Nyx leyó en voz alta `appaction({"app": "Rocket League", "action": "jump"})`

**Causa, en tres pasos:** (1) el LLM intentó actuar dentro del juego con `app_action`; (2) la validación lo rechazó y Nyx reintentó pasándole el error; (3) en el reintento el modelo escribió dos llamadas como texto, separadas por «;» y tras una cabecera `[acciones]`, y el intérprete de llamadas escritas (`brain/textcalls.py`) no lo reconoció, así que se leyó tal cual.

**Qué hacer:**

1. **Negativa fija antes del LLM** si hay un juego en primer plano y la frase pide hacer algo en él (saltar, disparar, avanzar, apuntar, construir…): «Dentro de los juegos no hago nada». Ya existe la lista de negativas fijas: se amplía con verbos de juego y con el contexto de partida.
2. `app_action` rechaza una app que sea juego **sin reintento** (el error no se le devuelve al LLM, se dice la negativa).
3. **Filtro de salida obligatorio:** nunca se dice en voz ni se muestra un texto que parezca código, JSON o una llamada a función. Si pasa, Nyx dice «No he podido hacerlo» y lo deja en el registro.
4. El intérprete de llamadas escritas acepta varias llamadas seguidas (`;`, saltos de línea) y la cabecera delante.

### 1.5 Otros fallos de la misma sesión

Apuntados en [ERRORES.md](ERRORES.md); la mayoría se resuelven con el trabajo del cerebro (0.6):

- «Bájate la calidad del cristal al mínimo» → `app_action zoom_out` sobre Rocket League (falta `nyx_control`).
- «¿Cuánto le queda a la alarma?» → «No hay ninguna alarma programada» (**inventó un estado del sistema**: falta `list_alarms` y una regla de «nunca afirmes nada del PC sin una herramienta»).
- «Ábrela» (tras crear una carpeta) → abrió Aimlabs: el router hizo coincidir «la» con un juego. Nombres de menos de 3 letras no se buscan de forma difusa, y lo creado o abierto entra en la memoria corta.
- «Cierra la carpeta que tengo abierta» → no sabe cerrar ventanas del Explorador por carpeta.
- «Busca qué aplicaciones ha creado Tepnyx» → buscó archivos en el disco en vez de en internet.
- «Explícame tu configuración para el modo partida» → abrió Ajustes en vez de explicarla (Nyx no se conoce a sí misma).
- Respuestas demasiado largas y de relleno («De nada, ¡estaré aquí cuando necesites algo más!»).

## 2. Versiones

### 0.5 — Partida e interfaz (cierre de la fase 5)

- Lo pendiente de probar de 5a (con juegos) y 5d.
- Las correcciones de la sección 1 (1.1, 1.3 y 1.4 completas; 1.2 y 1.5 pasan a la 0.6).
- Cerebro de partida y objetivo de FPS en la SPEC.

**Para cerrar:** una partida de Rocket League (y otro juego, por ejemplo Valorant) de 20 minutos hablando con Nyx sin tirones medidos con PresentMon, en el PC; la cola diferida funciona con 3 acciones; nunca se lee código en voz alta (prueba automática).

### 0.6 — Cerebro (fase 6a)

El salto grande: que Nyx entienda casi todo, haga casi todo lo que se puede hacer en Windows sin riesgo y busque lo que no sabe. Diseño en la sección 3.

- Bucle de agente: actuar, ver el resultado y seguir (hoy hace un plan de una vez).
- Dos niveles de cerebro (rápido y grande) y selección de herramientas por relevancia.
- Búsqueda en internet con fuentes, lectura de páginas y resumen.
- **Aprender a hacer cosas:** buscar cómo se hace, proponer los pasos, hacerlo con permiso y recordarlo.
- Nyx se conoce a sí misma (sus funciones y sus ajustes) y nunca inventa el estado del PC.
- Personalidad: tono configurable (cercano por defecto), respuestas cortas.
- Asistente contextual básico: sabe qué app usas y adapta respuestas y acciones.
- El resto de herramientas de la SPEC (`web_search`, `get_weather`, `system_power`, `system_info`, `clipboard`, `type_text`, `toggle_wifi`/`bluetooth`, `set_brightness`, `screen_record`, `nyx_control`, `run_powershell`) y lo marcado F6 en [ACCIONES.md](ACCIONES.md): ver y cancelar alarmas, alarmas repetidas, cronómetro, qué suena, cambiar la salida de audio, escritorios virtuales…
- Batería de 300+ frases (y después 1.000) en la integración continua, con informe por modelo.
- Elección del modelo final con los requisitos ya medidos (mínimo 8 GB de VRAM y 16 GB de RAM; recomendado 12 GB y 32 GB). Pendiente de esas pruebas: arranque de 23 s en el portátil (objetivo 10 s), RAM del núcleo (~800 MB frente a 600) y los fallos de Whisper en el portátil (ERRORES.md), que se corrigen más adelante.
- Verificación de voz (ECAPA), si sus condiciones de uso lo permiten (pendiente desde la fase 4).

**Para cerrar:** ≥ 95 % en la batería, < 1,5 s a la primera palabra con el modelo rápido, cero estados inventados en las preguntas sobre el PC, y que el usuario lo use un par de días sin apuntar fallos graves.

### 0.7 — Extensiones (fase 6b)

Lo que hay que **dejar preparado en esta versión** para que, desde la 1.0, se instalen extensiones sin actualizar Nyx. Diseño completo en la sección 4.

- Formato de paquete `.nyxext`, manifiesto, permisos y ciclo de vida (instalar, actualizar, desactivar, desinstalar).
- Proceso aislado para el código de las extensiones, con todo el acceso al sistema pasando por Nyx.
- Firma de Tepnyx, lista de revocación y modo desarrollador.
- Tipos: herramientas, acciones por app (sin código), formas de Nyx, preajustes de configuración, modos y conocimiento.
- **La forma actual de Nyx pasa a ser la forma predeterminada** dentro de este sistema (prepara la fase 7).
- Ajustes → Extensiones.
- SDK (`nyx-sdk`), plantilla, ejemplos y documentación, **todo con licencia MIT** (decisión del 2026-11-11), herramienta de línea de órdenes (`nyx-ext new / validate / pack / run`) y documentación con tres ejemplos: una herramienta, una forma y un modo.
- **Modos (base):** el sistema de modos y Partida (el modo partida actual), Trabajo, Noche y Privacidad. Diseño en la sección 5.
- Extensiones oficiales de prueba, gratuitas: OBS básico (grabar, directo, cambiar de escena) y Spotify (poner algo concreto).

- **Prioridad (2026-11-12): la gestión de extensiones y su documentación tienen que quedar
  muy bien hechas**, porque gran parte de las funciones nuevas llegarán como extensiones.
  Documentación para desarrolladores completa: cómo empezar, referencia de la API y del
  manifiesto, permisos, buenas prácticas (descripciones cortas para el modelo, grupos de
  herramientas y sus palabras clave: `tools/groups.py` y `docs/benchmarks/grupos-6.20b.md`),
  pruebas y publicación.
- **Índice de grupos de último recurso** (antes tarea 6.20c): con muchas extensiones no caben
  todas las herramientas y los grupos rotan; si el selector no sabe qué grupo es, el modelo
  elige en un índice de una línea por grupo.

**Para cerrar:** las tres extensiones de ejemplo se instalan, actualizan y desinstalan sin reiniciar Nyx; una extensión que se cuelga o intenta algo sin permiso no afecta a Nyx (pruebas automáticas); alguien que no sea yo (Claude) ni tú puede hacer una con la documentación (lo ideal: un amigo).

### 0.8 — Organización y seguridad (fase 6c)

- **Productividad:** notas rápidas, listas y tareas (locales, en SQLite), dictado («escribe lo que te diga» en la app activa, con `type_text`), resúmenes del portapapeles, del texto seleccionado o de un documento, documentos recientes («abre el último Word»), calendario local sencillo (citas y avisos; importa `.ics`) y recordatorios por contexto («cuando abra Discord, recuérdame…»).
- **Seguridad básica:** bloquear el PC por voz, modo Privacidad completo (sección 5), qué programas usan o han usado el micrófono y la cámara (el registro de privacidad de Windows lo guarda por usuario), ocultar ventanas de apps concretas.

**Para cerrar:** cada función con sus frases en la batería y sus pruebas.

### 0.9 — Beta pública (fase 6d)

Lo que la SPEC ya tenía en la fase 6 de distribución, más lo que pide abrir el código:

- Instalador propio con la onda de «Nyx listo» ([INSTALADOR-Y-MOTOR-GRAFICO.md](INSTALADOR-Y-MOTOR-GRAFICO.md)) que **instala y deja preparados el cerebro, Whisper y la voz**, arranque con Windows y actualizaciones con Velopack.
- **Primer arranque interactivo:** el asistente actual pasa a ser una conversación con Nyx (sección 11). Incluye **confirmar con el usuario la ciudad** detectada con la ubicación de Windows (2026-11-12).
- Pruebas de cortes de luz simulados.
- Datos de uso anónimos (servicio a elegir, por ejemplo Aptabase): **que el envío funcione de verdad** (hoy solo existe el permiso en Ajustes → Privacidad; recordado el 2026-11-12).
- **Contactar con soporte desde Ajustes → Ayuda** (2026-11-12): un botón para cualquier problema o duda. Falta decidir el canal (correo, formulario web, Discord de Tepnyx) y qué se adjunta (siempre con permiso: versión, registros recientes sin datos personales).
- **Voz propia de Nyx** (2026-11-12): entrenar un modelo de voz con la voz de una persona que ya ha aceptado. Antes de usarla, su consentimiento por escrito (uso, distribución en una app de código abierto y posibilidad de retirarlo) y comprobar la licencia del motor y del entrenamiento.
- La lista de `CLAUDE.md` antes de hacer público el repositorio: licencia y CLA, `SECURITY.md`, `CONTRIBUTING.md`, revisión de secretos, auditoría de licencias, SignPath.
- Beta abierta con un grupo pequeño (Discord de Tepnyx).

### 1.0 — Lanzamiento

- Versión estable.
- **Web de extensiones** en tepnyx.com: ficha de cada extensión, permisos que pide, botón «Instalar en Nyx» (enlace `nyx://`), política de revisión y portal para desarrolladores (subir, estado de la revisión, documentación).
- Normas para desarrolladores, términos y política de privacidad (sección 8.4).
- Extensiones oficiales gratuitas: OBS básico, Spotify, Discord (lo permitido, sección 4.8), Hue o Home Assistant (luces).

### 1.1 — Personalización y streaming (fase 7)

- **Fase 7:** formas de Nyx (cuadrado, gato, cara…) como extensiones de forma, ubicaciones (esquinas, oculto, brillo en los bordes) y tamaños.
- **Nyx Overlay** (opcional, desactivado por defecto): una ventana pequeña aparte con temperatura, FPS, música, avisos y accesos directos. Ver sección 7: cambia un principio de la SPEC.
- **Modos Streaming y Relax.**
- Primeras **extensiones de pago de Tepnyx**: OBS Pro y Rendimiento en juegos (sección 8).

### 1.2 — Vision

- Nyx entiende lo que hay en pantalla y responde sobre ello («¿qué pone aquí?», «resume esta página», «¿qué error es este?»). Modelo de visión local (por ejemplo Qwen2.5‑VL 7B, Apache 2.0) cargado solo al usarlo, y OCR de Windows para lo rápido.
- **Siempre con permiso y a petición:** nunca mira por su cuenta, nunca en juegos, nunca guarda la imagen, y se ve un aviso mientras mira. Apps excluidas en ajustes (gestores de contraseñas, banca).
- Asistente contextual avanzado: lee el control con foco y el texto seleccionado con UI Automation (no en juegos).

### 1.3 — Privacidad avanzada

- Programas en ejecución sin firma o en rutas raras («¿hay algo raro abierto?»), sin pretender ser un antivirus.
- Avisos de programas nuevos que se inician con Windows (claves `Run`, carpeta Inicio y tareas programadas).
- Privacidad en directo: ocultar avisos mientras compartes pantalla y detectar información privada en la salida de OBS (correos, direcciones, contraseñas) con Vision. Va dentro de la extensión de streaming.
- Calendarios externos (Outlook, Google) como extensiones con permiso explícito.

### 2.0 — Ecosistema

- **Nyx Plus** (opcional, de pago): servicios que le cuestan dinero a Tepnyx (sección 8).
- Extensiones de pago de otros desarrolladores en la web, con reparto de ingresos.
- Inglés como segundo idioma.
- Lo que digan los datos de uso y las sugerencias.

## 3. Cerebro: cómo Nyx llega a hacer casi todo (0.6)

### 3.1 Bucle de agente

Hoy el LLM devuelve un plan de una vez y Nyx lo ejecuta. Para tareas abiertas eso no basta. El nuevo bucle:

1. El router resuelve lo frecuente sin LLM (igual que ahora: < 500 ms).
2. Si no, el modelo rápido decide: responder, actuar o pasar al grande.
3. Para actuar: llama a herramientas, **ve el resultado** y decide el siguiente paso (máximo ~6 pasos y ~20 s, con «pensando» visible y «Nyx, para» para cortar).
4. Cada paso pasa por `SafetyGuard`, igual que ahora. El LLM nunca decide el riesgo.

### 3.2 Dos niveles de cerebro

| | Rápido | Grande |
| --- | --- | --- |
| Para qué | Elegir herramientas, respuestas cortas, seguimiento | Explicar, comparar, redactar, planes largos, resumir webs |
| Modelo | El 7B (local) | La nube opcional (2.0), con la clave del usuario o con Nyx Plus; el 14B local se descartó el 2026-11-11 |
| Cuándo | Siempre | Si el rápido lo pide, si la pregunta es larga o con «piénsalo bien» |
| En partida | El 7B, en la gráfica | Nunca |

Hasta la 2.0, solo el nivel rápido: lo que no sepa, lo busca en internet (sección 3.5).

### 3.3 Muchas herramientas sin saturar al modelo

Con las herramientas propias y las de las extensiones el catálogo pasará de 25 a cientos. A cada petición solo se le pasan las ~15 más relevantes, elegidas con un modelo de embeddings pequeño y multilingüe (licencia MIT o Apache, < 500 MB, en CPU) más las de la app activa. Es lo que la SPEC ya preveía para la fase 6.

### 3.4 Hacer casi todo en Windows

Además de las herramientas concretas, tres herramientas genéricas cubren lo que no tenga una propia:

- `ui_action`: pulsar un botón, marcar una casilla o leer un texto **por su nombre** en cualquier app que no sea un juego, con UI Automation de Windows (sin mover el ratón). Amarilla; roja si el botón dice «Eliminar», «Enviar», «Comprar»…
- `run_powershell`: como en la SPEC (roja siempre, se enseña el comando). Se añade una **lista de órdenes de solo lectura** (`Get-…`) que pueden ser verdes para responder preguntas sobre el PC.
- `install_app`: instalar o desinstalar programas con winget (roja; si Windows pide administrador, lo pide Windows, nunca Nyx).

### 3.5 Buscar en internet

- **Proveedor intercambiable** (`SearchEngine`), como el resto de piezas. Lo ideal para el usuario es **su buscador predeterminado** (el del navegador), pero leer sus resultados desde un programa puede ir contra sus condiciones y romperse con cualquier cambio de la web; DuckDuckGo tampoco tiene API oficial y las APIs con clave tienen límites o coste. Se valora en el plan de la 0.6 (decisión del 2026-11-11), con estas opciones: el buscador predeterminado, Wikipedia para conocimiento, una API con plan gratuito y, para Nyx Plus, una de pago. Abrir la búsqueda en el navegador del usuario siempre está permitido y es el respaldo.
- Leer la página (extracción del texto principal con trafilatura, Apache 2.0) y resumirla con el modelo grande, **siempre con la fuente en la burbuja**.
- Nyx busca sola cuando no sabe algo o es de actualidad, y lo dice («Lo busco…»). Se puede desactivar.
- El contenido de las webs nunca da órdenes (SPEC sección 8): va al modelo marcado como datos y no puede llamar a herramientas por sí mismo.

### 3.6 Aprender a hacer cosas

«Nyx, pon la barra de tareas a la izquierda» y Nyx no sabe:

1. Lo dice y pregunta: «No sé hacerlo todavía. ¿Lo busco?».
2. Busca cómo se hace y redacta una **receta** usando solo sus herramientas (abrir esta página de Configuración, pulsar este botón…) o, si no hay otra, una orden de PowerShell.
3. Enseña los pasos y la fuente en una burbuja: **nada se ejecuta sin que el usuario lo vea y lo apruebe**. Lo rojo sigue siendo rojo; la lista de bloqueo sigue valiendo.
4. Si sale bien, la guarda como habilidad aprendida (con la fuente) y la próxima vez la hace directamente.
5. Ajustes → Cerebro → Habilidades aprendidas: ver, probar, editar y olvidar.

Las recetas que funcionen pueden mandarse (con permiso) a Tepnyx, revisarse y convertirse en funciones oficiales o en extensiones.

### 3.7 Que Nyx no invente

- **Nunca afirma nada del PC sin una herramienta** (alarmas, archivos, ventanas, ajustes). Si no tiene herramienta, dice que no lo sabe.
- **Se conoce a sí misma:** un documento interno con lo que sabe hacer y qué hace cada ajuste (sale de la SPEC y de ACCIONES), para responder «¿qué puedes hacer en partida?» o «explícame tu modo partida».
- Memoria a largo plazo opcional y visible: preferencias y datos que el usuario le cuente («mi equipo es el Betis»), siempre consultables y borrables en Privacidad.
- **Aprende de lo que hace el usuario:** dónde escucha música (si siempre es YouTube, «pon música» va a YouTube y no a Spotify), qué navegador o perfil usa, qué apps abre juntas. Se ve y se corrige en Ajustes → Cerebro.

### 3.8 Personalidad

- Tono en Ajustes → Respuestas: cercano (predeterminado), neutro o divertido. Siempre breve.
- Frases propias para los momentos repetidos (activarse, hecho, error), variadas para no sonar a máquina.
- Las extensiones pueden añadir personalidades (sección 4.3).
- **Personalidad automática (pedido el 2026-11-12, para más adelante; difícil):** que el tono
  cambie solo según la conversación y el tono del usuario (más serio si está con prisa o
  enfadado, más bromista si él bromea…). Los ajustes manuales siguen existiendo: fijan el
  tono o dejan que se adapte. Ojo con la caché del prefijo: el tono no puede ir en el prompt
  de sistema si cambia a mitad de uso (iría en el mensaje del usuario).

### 3.9 Aprender cómo habla el usuario (pedido el 2026-11-12)

- Con cada uso, Nyx entiende mejor la forma de hablar del usuario (sus palabras, sus
  apodos para las apps, sus errores típicos de pronunciación que Whisper transcribe mal) y
  ajusta su forma de expresarse para acertar más. Base: los atajos aprendidos (SPEC 6),
  las correcciones («no, eso no») y el registro de acciones; todo local y visible en
  Ajustes → Cerebro, con opción de borrarlo.

## 4. Plataforma de extensiones (0.7)

### 4.1 Principios

1. **Nyx no se actualiza para instalar una extensión.** Las extensiones se descargan, verifican y cargan en caliente.
2. **Ninguna extensión toca Windows directamente.** Piden cosas a Nyx a través de su API y Nyx decide según los permisos aceptados, el riesgo y el modo partida. Así se mantienen todas las reglas de la sección 8.
3. **Permisos a la vista**, como en un móvil: se aceptan al instalar y si una actualización pide más, se vuelven a preguntar.
4. **Firmadas por Tepnyx** tras la revisión. Sin firma, solo en modo desarrollador.
5. **Fáciles de hacer:** lo sencillo sin programar (JSON) y lo complejo en Python con un SDK documentado.
6. **Nada dentro de los juegos, nunca:** la API no tiene ninguna forma de enviar teclas o leer la pantalla de un juego, así que ninguna extensión puede hacerlo aunque quiera.

### 4.2 El paquete

Un archivo `.nyxext` (un zip) con:

```text
manifest.json      Identidad, versión, tipos, permisos, API de Nyx compatible
icon.png
README.md          Lo que se ve en la web y en Ajustes
tools/             Herramientas (Python) — opcional
actions.json       Acciones por app sin código — opcional
skin/              Forma de Nyx — opcional
modes/             Modos — opcional
presets/           Preajustes de configuración — opcional
knowledge/         Textos que Nyx puede consultar — opcional
locales/           Frases y descripciones (es, en)
signature          Firma de Tepnyx (la añade la revisión)
```

Ejemplo de manifiesto:

```json
{
  "id": "tepnyx.obs-pro",
  "name": "OBS Pro",
  "version": "1.2.0",
  "author": "Tepnyx",
  "nyx_api": ">=1.0 <2.0",
  "kinds": ["tools", "mode"],
  "permissions": ["net:localhost:4455", "secrets", "ui:panel"],
  "game_policy": { "obs_scene": "allowed", "obs_zoom": "allowed" },
  "license": { "type": "paid", "product": "obs-pro" }
}
```

### 4.3 Tipos de extensión

| Tipo | Qué es | Cómo se hace | Ejemplos |
| --- | --- | --- | --- |
| Acciones por app | Atajos de una app para `app_action` | JSON, sin código | Figma, Photoshop, DaVinci |
| Herramientas | Funciones nuevas que el LLM puede usar | Python con el SDK | Discord, OBS, Steam, Hue |
| Forma de Nyx | Otro aspecto para el indicador | Shader GLSL con un contrato fijo; más adelante animaciones con estados (Rive o Lottie, a evaluar licencias) | Gato, cara, esfera |
| Modo | Un perfil con disparadores y acciones (sección 5) | JSON | «Modo estudio», «Modo cine» |
| Preajuste | Un conjunto de ajustes de Nyx | JSON (solo los ajustes editables) | «Silenciosa», «Para streamers» |
| Conocimiento | Textos que Nyx consulta para responder | Markdown | Guía de un juego, manual de una app |
| Personalidad | Tono y frases propias | JSON | «Nyx pirata» |
| Widget (1.1) | Un bloque para Nyx Overlay | HTML/Svelte en la WebView aislada | FPS, temperatura, chat de Twitch |

**Formas de Nyx:** el contrato son unos uniforms fijos (estado, nivel de audio, fase, color elegido, tamaño, tiempo) y una caja máxima declarada, para que Nyx respete el hueco de 14 px con los paneles. Se dibujan en la WebView sin red ni acceso a nada: una forma no puede hacer daño. La forma cuadrada actual se convierte en la primera (`tepnyx.forma-nyx`).

### 4.4 Cómo se ejecutan

- **Sin código** (acciones, modos, preajustes, conocimiento, personalidad, formas): Nyx los lee y los valida contra un esquema. No ejecutan nada.
- **Con código** (herramientas): cada extensión corre en **su propio proceso Python**, con:
  - un Python incluido con Nyx y sus dependencias dentro del paquete (sin `pip` al instalar);
  - un token de Windows de baja integridad o AppContainer (a investigar cuál encaja mejor), para que el propio Windows le impida leer los archivos del usuario o abrir la red por su cuenta;
  - un objeto de trabajo de Windows (como `winjob.py`) con límites de CPU y memoria; en partida, prioridad mínima;
  - comunicación con Nyx por una tubería con nombre (JSON-RPC). Todo lo que quiera hacer (abrir una URL, leer un archivo, conectar a OBS, guardar una clave) se lo pide a Nyx, que comprueba el permiso.
- Si una extensión se cae, se reinicia; si se cae 3 veces seguidas, se desactiva y se avisa. Nyx sigue funcionando.
- Más adelante se puede añadir WebAssembly (wasmtime, Apache 2.0) como segundo motor, aún más aislado y para cualquier lenguaje. No hace falta para la 1.0.

### 4.5 Permisos

| Permiso | Qué permite | Riesgo mínimo de sus herramientas |
| --- | --- | --- |
| `net:<host>` | Conectar con ese servidor (p. ej. `localhost:4455` para OBS) | Verde |
| `files:read:<carpeta>` / `files:write:<carpeta>` | Leer o escribir en esa carpeta del usuario | Verde / amarillo |
| `apps:launch`, `apps:control:<app>` | Abrir apps; usar `app_action` o `ui_action` en una app | Verde / amarillo |
| `audio`, `media` | Volumen y multimedia | Verde |
| `clipboard:read` / `clipboard:write` | Portapapeles | Verde |
| `notify`, `ui:panel`, `ui:widget` | Avisos, paneles de Nyx, widgets del Overlay | Verde |
| `secrets` | Guardar claves en el Administrador de credenciales de Windows | — |
| `llm` | Usar el cerebro de Nyx (con cupo) | — |
| `messages:<servicio>` | Enviar mensajes a otras personas | **Rojo siempre** |
| `screen` (1.2) | Pedir una captura con el permiso de Vision | Amarillo |

`SafetyGuard` aplica el riesgo mínimo del permiso aunque la extensión declare otro más bajo. **No existe ningún permiso para enviar teclas a un juego, leer su memoria o inyectarse en él.**

### 4.6 Firma, revisión y revocación

1. El desarrollador sube el paquete al portal de tepnyx.com.
2. **Revisión automática:** manifiesto y esquemas, permisos coherentes con lo que hace, análisis del código (llamadas prohibidas, ofuscación, binarios sin explicar), tamaño y licencias de dependencias.
3. **Revisión manual del equipo de Tepnyx** con unas normas públicas. Prohibido: trampas o automatizar juegos, recoger datos que no se declaren, publicidad, minería, saltarse los permisos, contenido ilegal o que suplante a otros.
4. Tepnyx firma el paquete (Ed25519; la clave privada fuera del repositorio, como la de las actualizaciones).
5. Nyx descarga cada día una **lista de revocación** firmada: si una extensión resulta dañina, se desactiva en todos los equipos.
6. **Modo desarrollador** (Ajustes → Extensiones): cargar una carpeta sin firmar para probarla, con la etiqueta «sin revisar» bien visible.

### 4.7 Actualizaciones y versiones de la API

- Las extensiones se actualizan solas desde la web, aparte de Nyx, igual que Nyx (descarga, verificación, cambio atómico).
- La API tiene su propia versión semántica (`nyx_api`). Nyx 1.x mantiene la API 1.x; lo que se vaya a quitar se avisa una versión antes.

### 4.8 Ejemplos de lo que se podrá hacer

- **OBS** (con obs-websocket, que viene con OBS): cambiar de escena, empezar o parar el directo, silenciar fuentes, marcadores, **zoom a la cámara** («Nyx, acércate») animando la transformación de la fuente, repetición instantánea. Básica gratis, Pro de pago (sección 8).
- **Discord:** lo que se puede hacer sin romper sus condiciones: silenciar, ensordecer, cambiar de canal (atajos y su API local para apps aprobadas), leer avisos. **Controlar la cuenta del usuario con un bot (self-bot) va contra las condiciones de Discord** y puede acabar en el cierre de la cuenta: no se permitirá en la revisión. Para mandar mensajes hay que usar lo que Discord ofrezca de forma oficial.
- **Cuando un servicio no deja hacer algo** (decisión del 2026-11-11), Nyx lo dice y ofrece guiar al usuario: «Discord no me permite hacer eso, pero puedo guiarte: abre los ajustes del servidor y…». Vale para cualquier app o servicio, propio o de una extensión: las herramientas pueden devolver «no permitido» con los pasos para hacerlo a mano, y Nyx los enseña en un panel.
- **Rendimiento en juegos:** FPS y tiempos de fotograma con PresentMon (ETW, sin tocar el juego), temperatura y uso de la GPU (ADLX en AMD, NVML en NVIDIA) y aviso por voz si los FPS caen o la GPU se calienta. PresentMon necesita permisos de registro de rendimiento de Windows: hay que ver cómo pedirlos una sola vez.
- **Spotify, Steam, Hue, Home Assistant, Twitch, YouTube**, y formas como el gato o la cara.

## 5. Modos (0.7 la base, 1.1 el resto)

Un modo es un perfil que cambia cómo se comporta Nyx y prepara el PC para algo. Es una pieza central y también un tipo de extensión.

**Qué tiene un modo:**

- **Disparadores:** por voz («modo trabajo»), automático (un juego en primer plano, OBS en directo, una app abierta, una hora) o desde la bandeja.
- **Al entrar y al salir:** acciones (abrir y colocar apps, volumen, luz nocturna, no molestar, luces…), que se pueden deshacer al salir.
- **Comportamiento de Nyx:** voz sí o no y a qué volumen, burbujas, monitor, tono.
- **Herramientas:** permitidas, diferidas y bloqueadas (lo que hoy es solo del modo partida pasa a ser de cualquier modo).
- **Extensiones** activas en ese modo.

Solo hay un modo activo, salvo los automáticos, que tienen prioridad: Partida > Streaming > el que haya elegido el usuario. Al acabar la partida se vuelve al modo anterior.

| Modo | Versión | Qué hace |
| --- | --- | --- |
| Partida | 0.7 (ya existe) | Lo de la SPEC sección 9 y la sección 1 de este documento, ahora como modo |
| Trabajo | 0.7 | Abre y coloca las apps elegidas, silencia lo que distrae, Nyx en burbujas y voz baja |
| Noche | 0.7 | Volumen bajo, voz de Nyx más suave, sin sonidos, luz nocturna y no molestar |
| Privacidad | 0.7 | Micrófono de Nyx solo con atajo, sin burbujas con contenido, sin búsquedas, oculta apps elegidas |
| Streaming | 1.1 | Con la extensión de OBS: avisos fuera de la pantalla compartida, comandos de escena y cámara, Nyx en capturas sí o no |
| Relax | 1.1 | Música (Spotify), luces (Hue/Home Assistant), entretenimiento |

A investigar: Windows no tiene una API pública para la luz nocturna ni para «no molestar». Hay formas no oficiales (registro, WNF) que pueden romperse con una actualización de Windows. Se probarán y, si no son fiables, el modo abre la página de Configuración correspondiente.

## 6. Dónde va cada idea

| Idea | Versión | Nota |
| --- | --- | --- |
| Nyx Vision | 1.2 | Con permiso, nunca en juegos |
| Nyx Overlay | 1.1 | Opcional; cambia un principio (sección 7) |
| Nyx Extensions | 0.7 (plataforma), 1.0 (web), 1.1 (de pago de Tepnyx), 2.0 (de pago de terceros) | |
| Modos: Partida, Trabajo, Noche, Privacidad | 0.7 | |
| Modos: Streaming, Relax | 1.1 | Necesitan las extensiones de OBS, Spotify y luces |
| Personalidad | 0.6 | |
| Asistente contextual | 0.6 (app activa), 1.2 (texto seleccionado y pantalla) | |
| Recordatorios, temporizadores, alarmas | Hechos; ver y cancelar en 0.6 | |
| Tareas, listas, notas rápidas | 0.8 | |
| Calendario y citas | 0.8 (local), 1.3 (Outlook y Google) | |
| Documentos recientes | 0.8 | |
| Dictado | 0.8 | |
| Resúmenes | 0.6 (webs), 0.8 (portapapeles, documentos) | |
| Bloquear el PC por voz | 0.6 (`system_power`) | |
| Modo privacidad | 0.7 | |
| Ocultar apps concretas | 0.8 | |
| Qué apps usan micrófono y cámara | 0.8 | |
| Programas desconocidos en ejecución | 1.3 | Sin hacerse pasar por antivirus |
| Apps que se inician con Windows | 1.3 | |
| Privacidad en streaming | 1.1 (ocultar avisos), 1.3 (detectar datos privados en OBS) | |
| Buscar en internet | 0.6 | |
| Aprender a hacer cosas | 0.6 | Siempre con aprobación |
| Avisos de FPS y temperatura | 1.1 | Extensión Rendimiento en juegos |
| Formas de Nyx (gato, cara) | 0.7 (el sistema), 1.1 (las formas) | |
| Controlar el juego («salta», «avanza») | **Nunca** | Principio 5 y anticheat |
| Primer arranque como conversación con Nyx | 0.9 | Con el instalador (sección 11); prototipo antes en la galería |

## 7. Cambios a la SPEC

Decididos el 2026-11-11: el 1 (Overlay, aprobado tal cual), Discord y servicios que no lo permiten (Nyx lo avisa y ofrece guiar, sección 4.8), el kit de extensiones con licencia MIT y la búsqueda en internet (se valora en la 0.6, empezando por el buscador predeterminado). Los demás se aplican a la SPEC en la versión que les toca.

1. **Principio 5 y Nyx Overlay (aprobado).** La SPEC dice «sin overlay dentro del juego». Se mantiene la prohibición de **inyectarse** en el juego, y permitir (opcional, desactivado por defecto) una ventana aparte encima de juegos en ventana sin bordes, que nunca toma el foco ni recibe clics. Con pantalla completa exclusiva no se puede ver sin inyectarse, así que el Overlay irá al otro monitor o no saldrá. Hay que medir que no cueste FPS (una ventana siempre encima puede obligar a Windows a componer el juego, que es justo por lo que hoy Nyx no se queda visible en reposo).
2. **Principio 5 y Vision.** Se mantiene «nunca leer la pantalla de un juego». Vision no funciona con un juego en primer plano.
3. **Rendimiento en juegos.** Leer los FPS con PresentMon no toca el juego (lo hace Windows), así que encaja con el principio 5. Se dice explícitamente en la SPEC.
4. **«Fuera de alcance (v1)»** pasa a «fuera de alcance (1.x)» y se añade «extensiones que actúen dentro de juegos».
5. **Sección 13:** nuevas secciones de Ajustes (Extensiones y Modos) y «Cerebro en partida».
6. **Sección 14:** el objetivo de FPS en partida (sección 1.1).
7. **Sección 16:** las fases 6 a 10 de este documento, con sus versiones.

## 8. Cómo ganar dinero sin cobrar por usar Nyx

Nyx es gratis, de código abierto y funciona en local: todo lo que hoy hace seguirá siendo gratis. Se cobra solo por tres cosas: **trabajo extra de Tepnyx** (extensiones avanzadas), **servicios que cuestan dinero mantener** (nube) y **apoyo voluntario**. Nunca publicidad ni venta de datos: chocaría con la sección 8 de la SPEC y con la confianza, que es lo que hace que alguien deje a un asistente controlar su PC.

### 8.1 Fuentes de ingresos

| Fuente | Qué es | Cuándo | Precio orientativo |
| --- | --- | --- | --- |
| Extensiones de pago de Tepnyx | OBS Pro (zoom de cámara, escenas por voz, repeticiones, privacidad en directo), Rendimiento en juegos (FPS, temperaturas, avisos, informes), packs de formas y personalidades | 1.1 | 3–9 € de pago único cada una, o un pack «Creator» |
| Nyx Plus (suscripción) | Cerebro en la nube para PCs sin gráfica potente (sobre todo portátiles), búsqueda web mejor, Vision en la nube, voces premium, copia de ajustes y habilidades entre PCs | 2.0 | 3–5 €/mes |
| Comisión de la web de extensiones | Un porcentaje de las extensiones de pago de terceros | 2.0 | 15–20 % (la media del mercado es 15–30 %) |
| Apoyo directo | GitHub Sponsors, Ko-fi o Patreon: nombre en los créditos, betas antes, una forma exclusiva de agradecimiento | 0.9 | Libre |
| Empresas y marcas | Licencia comercial del núcleo para quien quiera usarlo sin publicar su código (posible gracias al CLA), versiones a medida para fabricantes de periféricos, cibercafés o centros de esports | 1.x | A negociar |
| Extensiones patrocinadas | Una marca paga a Tepnyx por hacer y mantener la extensión oficial de su producto, siempre indicado | 1.x | A negociar |

### 8.2 Lo que más sentido tiene al principio

1. **Extensiones de pago de Tepnyx** (1.1): ingreso directo, sin infraestructura cara, y encajan con el público (gaming y streaming). OBS Pro es el mejor candidato.
2. **Apoyo directo** desde la beta: cuesta poco ponerlo y crea comunidad.
3. **Nyx Plus** solo cuando haya usuarios: la nube cuesta dinero cada mes, así que hay que tener claro el número antes.

### 8.3 Cómo se cobra sin cuenta

- Pago con una plataforma que haga de **vendedor registrado** (Lemon Squeezy o Paddle): se encarga del IVA de cada país de la UE y del resto del mundo, que si no es un trabajo enorme. Stripe es más barato pero el IVA lo gestiona uno.
- **Las extensiones de pago son siempre de pago único**, de Tepnyx y de terceros: nunca una suscripción, y la compra no caduca (decisión del 2026-11-14). La única suscripción posible es Nyx Plus, porque la nube cuesta dinero cada mes.
- Se entrega una **licencia firmada** (archivo o código) que Nyx comprueba sin conexión. Sin cuenta para lo gratuito; para Nyx Plus sí hará falta una cuenta, opcional y solo para eso (ya lo prevé la SPEC).
- Como Nyx es de código abierto, alguien podría saltarse la comprobación. Es normal y se asume: quien paga lo hace por las actualizaciones, el soporte y por apoyar el proyecto.

### 8.4 Temas legales a revisar (con un profesional)

- **GPL‑3.0 y extensiones de pago:** una extensión en su propio proceso que habla con Nyx por una tubería se considera en general una obra aparte, así que puede tener su propia licencia. Por eso todo el kit de extensiones (SDK, plantillas, ejemplos y documentación) va con licencia MIT (decidido el 2026-11-11): si fuera GPL, toda extensión que lo use tendría que ser GPL. Las extensiones de Tepnyx no tienen problema, porque Tepnyx es dueña del código (gracias al CLA).
- **Web de extensiones:** normas para desarrolladores, términos de uso, política de privacidad (RGPD) y las obligaciones de la Ley de Servicios Digitales de la UE para plataformas que alojan contenido de otros (aviso de contenido ilegal, identificación de vendedores de pago).
- **Ingresos:** darse de alta como autónomo o empresa en España cuando empiecen las ventas.

### 8.5 Costes a tener en cuenta

Alojamiento de la web y de los paquetes, el tiempo de revisión de extensiones (crece con la comunidad: la revisión automática ayuda), la nube de Nyx Plus (lo único caro de verdad) y las comisiones de pago (≈ 5 % + una cantidad fija por venta en los vendedores registrados). La firma de código para Windows con SignPath es gratis para proyectos de código abierto.

## 9. Riesgos y preguntas abiertas

| Riesgo o pregunta | Qué propongo |
| --- | --- |
| Un modelo local de 7–8B tiene un techo de comprensión | Dos niveles de cerebro, búsqueda web, habilidades aprendidas y, para quien quiera, la nube (gratis con su clave, o Nyx Plus) |
| Una extensión maliciosa que pase la revisión | Proceso aislado, permisos por Nyx, lista de revocación y revisión con reglas públicas |
| Revisar extensiones lleva mucho tiempo | Revisión automática primero; al principio solo extensiones de Tepnyx y de desarrolladores invitados |
| Anticheat (Vanguard, EAC…) puede no gustarle algo | Nada se inyecta ni toca el juego; PresentMon y las ventanas aparte son lo que usan las herramientas habituales. Probar con Valorant y Rocket League antes de cada versión |
| Funciones de Windows sin API pública (luz nocturna, no molestar) | Probar las vías no oficiales y tener siempre la página de Configuración como respaldo |
| Búsqueda web gratis y legal | Elegir el proveedor en el plan de la 0.6 con precios y condiciones actuales |
| Requisitos mínimos | Medidos ([requisitos](benchmarks/requisitos.md)): 8 GB de VRAM y 16 GB de RAM. Con 8 GB, el cerebro de partida y Vision tienen que caber; cada función nueva se mide en el portátil |
| El primer arranque interactivo depende de que todo esté instalado | Lo instala el instalador; si falta algo o no hay micrófono, el mismo recorrido funciona con botones y texto (sección 11) |

## 10. Próximos pasos

1. Empezar por la **0.5**: plan corto de las correcciones del modo partida (sección 1) con los archivos que voy a tocar, para tu visto bueno.
2. Al empezar cada versión, pasar a la SPEC lo que le toca de este documento.

## 11. Instalación y primer arranque interactivos (0.9)

La idea (2026-11-11): que instalar y preparar Nyx sea una experiencia. El asistente de primer arranque actual (5d‑2, una ventana con pasos) pasa a ser **una conversación con Nyx**: aparece la forma, habla, enseña paneles con las opciones y el usuario contesta por voz o con un clic.

### 11.1 Dos partes

1. **Instalador** (sin conversación todavía, porque Nyx aún no puede oír ni hablar): instala Nyx, Ollama si falta, el cerebro recomendado para la gráfica, Whisper y la voz, con progreso real y verificación de hash. Al final hace el **calentamiento** (cargar el cerebro y una transcripción de prueba), para que la primera frase no tarde: en el portátil la primera transcripción tarda ~17 s porque se compilan los shaders. Termina con la onda de «Nyx listo».
2. **Primer arranque:** Nyx aparece y guía la configuración hablando.

Para no hacer esperar: Whisper y la voz pesan ~1,5 GB y el cerebro ~4,7 GB. Se descargan primero los de voz; si la conversación puede empezar antes de que acabe el cerebro, empieza con los pasos que no lo necesitan y el cerebro sigue bajando en segundo plano (Nyx lo dice: «Mientras termino de descargar mi cerebro, vamos a conocernos»).

### 11.2 Cómo funciona cada paso

Ejemplo, el paso del color:

1. Nyx habla: «Ahora, a ver qué color me queda bien. Elige uno de los de abajo».
2. Debajo de Nyx aparece un panel con los 19 colores y su nombre.
3. El usuario dice «turquesa» (o hace clic). Nyx cambia de color al momento con un pequeño rebote y dice: «¡Wow, me encanta este! ¿Lo dejamos así?».
4. «Sí», «vale», «perfecto» o el botón **Confirmar** lo guardan; «otro», «no» o decir otro color siguen probando.

Así con todos los pasos, siempre con estas reglas:

- **Lo que dice Nyx está escrito de antemano** (con varias versiones de cada frase para que no se repita), no lo genera el LLM: así es rápido, siempre igual de bien y sin sorpresas. Lo que dice se ve también en el panel, en texto pequeño.
- **Lo que dice el usuario se entiende contra las opciones del paso:** Whisper transcribe y se compara con los nombres de las opciones y con «sí/no/otro/atrás/saltar» (como la confirmación por voz actual). Es fiable, funciona aunque el cerebro aún se esté descargando y no da respuestas raras. El LLM solo entra si el usuario pregunta algo fuera del guion («¿y qué es el modo partida?»), y contesta con lo que Nyx sabe de sí misma (sección 3.7) antes de volver al paso.
- **Todo se puede hacer sin voz:** cada paso tiene sus botones, y si no hay micrófono o el usuario lo prefiere, el recorrido entero funciona con clics y teclado (y Nyx sigue hablando, o en silencio si se le pide).
- **Interrumpir:** hablar mientras Nyx habla la corta, como ahora.
- **Atrás y Saltar** por voz y con botones, con las mismas reglas que el asistente actual; lo que no se toca se queda como está.
- **Lo que no puede ser por voz:** el permiso de los datos de uso anónimos se da solo con un clic en la casilla (para que el consentimiento sea claro), como las confirmaciones de más de 50 archivos.
- **Se repite desde Ajustes → Ayuda**, como ahora.

### 11.3 Recorrido propuesto

| Paso | Nyx dice (idea) | Panel | El usuario |
| --- | --- | --- | --- |
| Hola | «¡Hola! Soy Nyx. Te voy a ayudar a prepararme, solo son un par de minutos» | — | «Vale» / Empezar / Saltar |
| Micrófono | «Di "Nyx" para ver si te oigo bien» | Nivel del micrófono y lista de micrófonos | Dice «Nyx»; si no le oye, ofrece elegir otro |
| Color | «A ver qué color me queda bien…» | Los 19 colores con su nombre | Nombre del color, «sí» |
| Tamaño | «¿Me prefieres más grande o más pequeña?» | Deslizador | «Más grande», «más pequeña», «así» |
| Paneles | «Y los paneles donde te enseño cosas, ¿de qué tono?» | Los 12 tintes, con un panel de ejemplo | Nombre del tinte, «sí» |
| Voz | Nyx habla con cada voz: «¿Te gusta cómo sueno así?» | Voces y velocidad | «Esta», «la siguiente», «más despacio» |
| Juegos | «Cuando juegues, no te molesto. ¿Prefieres que solo te hable o que no haga nada?» | Las opciones de «Nyx en partida» | Opción por voz o clic |
| Tu equipo | «Voy a aprenderme tus apps y juegos» | Escaneo con progreso; Everything opcional | — |
| Datos anónimos | «¿Me ayudas a mejorar? Solo si quieres» | Lo que se envía y lo que nunca | **Solo clic** |
| Pruébame | «Pídeme algo. Por ejemplo: "abre el bloc de notas"» | Tres ejemplos | Hace una petición de verdad |
| Listo | «¡Listo! Llámame cuando quieras diciendo "Nyx"» | Atajos de teclado | — |

### 11.4 Qué se reutiliza

- El servicio del asistente actual (`core/nyx/setup/service.py`): estado, descargas, escaneo y prueba del micrófono.
- Los ajustes que ya se aplican al momento (color, tamaño, tinte, fuente) y la forma de Nyx real como vista previa.
- Los paneles sobre el motor de cristal (sección 12 de la SPEC) y el hueco de 14 px con Nyx.
- La confirmación por voz con gramática cerrada.

Lo nuevo es un **guion de pasos** en el núcleo (qué dice Nyx, qué panel enseña, qué respuestas acepta y qué hace con cada una), pensado para poder reutilizarlo más adelante en otros recorridos guiados (por ejemplo, al instalar una extensión o en el tutorial de un modo). Antes de integrarlo, un prototipo en la galería para aprobar cómo se ve y cómo suena.

**Para cerrar:** el recorrido completo por voz y solo con clics en los dos equipos, sin esperas de más de 1 s entre lo que dice el usuario y la respuesta de Nyx.
