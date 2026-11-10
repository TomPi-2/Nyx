# Propuesta: motor gráfico de cristal, instalador propio y onda de «Nyx listo»

**Estado:** el motor gráfico (apartado 2) entra antes de la fase 5c (acordado el 2026-11-10) y tiene una primera versión completa en `ui/src-tauri/src/glass` con una galería de ejemplos (bandeja → «Motor gráfico (ejemplos)»), pendiente de que el usuario la vea y la apruebe. Lo demás sigue siendo propuesta. **Todavía no cambia `docs/SPEC.md`.**
Recoge lo que pidió el usuario el 2026-11-10 y el análisis de viabilidad hecho ese día, para poder retomarlo desde VS Code.

## 0. Decisiones del usuario tras ver la galería (2026-11-10)

- **Ruta A descartada.** El pincel de fondo de Windows (`HostBackdropBrush`) no está disponible en el portátil de pruebas, así que el nivel «Compositor» se quita. Quedan Alto, Medio y Bajo (apartado 2.5).
- **Calidad en Ajustes:** «Auto» (predeterminado) o un nivel concreto.
  - En Auto, el motor baja solo con batería, ahorro de energía, transparencias de Windows desactivadas o una GPU que no llega.
  - Con un nivel concreto, el motor lo respeta, salvo en partida, donde pasa a Bajo **sin excepción**. Ajustes debe decirlo junto al selector: «En partida se cambia a Bajo automáticamente, sin excepción».
- **Valores predeterminados:**

  | Parámetro | Valor |
  | --- | --- |
  | Amplitud del borde | 3,5 px |
  | Desenfoque | 0,6 |
  | Refracción | 10 px |
  | Saturación | 1,15 |
  | Velocidad | ×1 |
  | Tinte gris | 0,45 |
  | Brillo | 0,35 |
  | Sombra | 0,4 |

- **Amplitud del borde personalizable en Ajustes:** una barra de 0 a 10, de 1 en 1, que va de 0 a 7 px (0,7 px por paso). El 5 (3,5 px) es el valor predeterminado.
- **Separación entre Nyx y los paneles:** el cuadrado blanco de Nyx y el rectángulo de la respuesta de texto (y cualquier otro panel de la isla) dejan siempre un espacio entre ellos. Nunca se solapan, contando también la ondulación del borde y la deformación de Nyx. Excepción: la ventana de Ajustes, que se mueve libremente como cualquier otra ventana.
- **El campo de texto para escribirle a Nyx también usa el motor.**
- La GPU que usa el motor en el portátil es la integrada (AMD Radeon Graphics).

Objetivo que lo une todo: que Nyx sea una experiencia completa y coherente, desde que se instala hasta que se usa a diario.

Cada apartado separa **lo que pidió el usuario** (requisitos, no se cambian sin hablarlo) de **la propuesta técnica** (hipótesis de Claude, sin probar en un equipo real: hay que validarlas con prototipos y mediciones antes de darlas por buenas).

## 1. Orden acordado

1. **Motor gráfico** (cristal en tiempo real, bordes líquidos, opción de blur gris o alternativa).
2. **Ventana de Ajustes y paneles** (respuesta, confirmación, deshacer, campo de texto) usando el motor.
3. **Instalador propio**, con el mismo estilo y componentes que Ajustes.
4. **Onda de cristal** (final de la instalación e indicador de «Nyx listo»), hecha con el motor.

El usuario quiere esperar a tener el motor antes de hacer la onda y las demás animaciones. No implementar la onda antes.

Falta decidir en qué fase entra cada cosa (ver «Preguntas abiertas»). Hoy la SPEC deja el «cristal nativo» para después de la v1 (sección 12, «Más adelante») y el instalador en la fase 6.

## 2. Motor gráfico

### 2.1 Lo que pidió el usuario

- Un motor **sencillo, de calidad y lo más optimizado posible**, pensando en el usuario.
- **Fondo predeterminado: cristal con un poco de opacidad**, al estilo del cristal de iOS (el usuario citó «iOS 27»), aunque con reflejos de menos calidad si los buenos gastan demasiado. El nivel de calidad lo decide Claude midiendo el coste.
- El cristal se ve **en tiempo real según lo que haya detrás**.
- **Ningún borde en ningún sitio.** La silueta de los paneles debe ser como la del cuadrado de Nyx: **ondula como un líquido no newtoniano**, y el efecto de cristal acompaña al movimiento del borde.
- Si ese movimiento consume mucho, **se puede desactivar en Ajustes**.
- Los **fondos de los textos** (burbujas) podrían llevar también esa animación en el borde.
- **Blur gris:** ver si merece la pena o si hay otra opción «chula y limpia» que gaste menos.
- El motor se usa para los fondos de los textos, la ventana de Ajustes, el instalador, la onda y otras animaciones futuras.

### 2.2 Punto de partida (ya medido en la fase 1)

De la sección 11 de la SPEC y `ui/src-tauri/src/glass.rs`:

- El `backdrop-filter` de CSS no desenfoca lo que hay detrás de una ventana transparente.
- El Acrylic de Windows 11 se ve sólido en ventanas que nunca toman el foco, actualiza con ~2 s de retraso y, recortado con una región, deja bordes en escalones.
- Por eso hoy se usa un tinte gris translúcido al 84 % dibujado en CSS.
- Requisitos ya escritos para el cristal nativo: coste de GPU mínimo, nunca capturar ni tocar la ventana de un juego y volver al tinte si no se puede.

Conclusión: para ver lo de detrás en tiempo real, o lo hace el compositor de Windows por nosotros o Nyx captura la pantalla y lo dibuja.

### 2.3 Rutas técnicas a prototipar

| Ruta | Cómo | A favor | En contra / por comprobar |
| --- | --- | --- | --- |
| **A. Compositor de Windows** (descartada el 2026-11-10: el pincel no está disponible; ver apartado 0) | `Windows.UI.Composition` con un pincel de fondo (`HostBackdropBrush` + efectos de desenfoque, tinte y saturación) y un recorte con geometría animada. | Lo dibuja el propio compositor: sin capturas, coste bajo, siempre al día. | Hay que comprobar que funciona en ventanas sin foco (el fallo del Acrylic puede ser de su política y no del pincel). Su lista de efectos no parece incluir desplazamiento, así que **no daría refracción real**, solo desenfoque. Se apaga si el usuario desactiva los efectos de transparencia de Windows. |
| **B. Captura + shader propio** | `Windows.Graphics.Capture` del monitor (sin borde amarillo ni cursor, con las ventanas de Nyx excluidas mediante `WDA_EXCLUDEFROMCAPTURE`) y un shader Direct3D 11 nativo en Rust que dibuja el cristal. La interfaz Svelte va encima con fondo transparente. | Control total: refracción, brillos, borde líquido y la onda. Es la única ruta que da el cristal «tipo iOS» completo. | Coste de GPU por capturar y procesar. El contenido protegido (DRM) sale en negro. Hay que resolver cómo se compone la capa nativa bajo la WebView de Tauri. |
| **C. Sin lo de detrás** | El tinte actual, mejorado con degradado, brillo especular y grano fino. | Casi gratis; ya funciona. | No es cristal real. Es el respaldo obligatorio. |

Pasar las imágenes capturadas a la WebView para dibujarlas con WebGL se descarta de entrada: copiar texturas a la WebView en cada fotograma es caro. El shader de la ruta B tiene que ser nativo.

**Propuesta:** un prototipo corto que mida A y B en el PC de referencia (RX 7700 XT) y en el portátil (RTX 3070 Laptop), y decidir con números. Es probable que el resultado sea una combinación por niveles de calidad (2.5).

### 2.4 Cómo mantener bajo el coste (ruta B)

- Capturar **solo mientras hay un panel visible**. En reposo, nada (0 % de GPU, como hoy).
- Procesar **solo la zona de detrás del panel**, no el monitor entero.
- Desenfocar a **resolución reducida** (un cuarto o menos) con un desenfoque de pocas pasadas (tipo Kawase dual).
- Redibujar el fondo **solo cuando cambia la pantalla** (la captura avisa cuando hay fotograma nuevo) y con tope de 30 Hz; la silueta puede animarse a 60.
- **Refracción solo en una franja junto al borde**, que es donde el cristal de iOS deforma la imagen; el centro solo necesita desenfoque y tinte.
- Reflejos sencillos: un brillo especular calculado con la forma, sin trazado ni mapas de entorno.
- Objetivo a confirmar con mediciones: mantenerse en la línea del indicador (sección 12: menos del 2 % de GPU).

### 2.5 Niveles de calidad

| Nivel | Qué incluye |
| --- | --- |
| Alto | Desenfoque en tiempo real + refracción en el borde + brillo especular + borde líquido |
| Medio | Desenfoque en tiempo real + tinte + brillo sencillo |
| Bajo | Tinte translúcido actual (ruta C) |

Aparte, un interruptor independiente para el **movimiento del borde**.

El motor baja de nivel solo, sin preguntar, cuando:

- hay una partida (sección 9): **nunca se captura con un juego abierto**, también por los sistemas antitrampas;
- Windows tiene desactivados los efectos de transparencia o activado «reducir movimiento» (este último solo para el movimiento);
- el equipo va con batería o con ahorro de energía;
- la captura falla o la GPU no da el rendimiento esperado.

### 2.6 Bordes líquidos

- Reutilizar la técnica de la forma de Nyx (`ui/src/overlay/shape`, prototipo `docs/prototipos/forma-nyx-v2.html`): campo de distancia de un rectángulo redondeado deformado con ruido de baja frecuencia, en bucle sin cortes.
- En los paneles, **amplitud pequeña** (unos pocos píxeles) y margen interior suficiente para que la ondulación nunca corte el texto ni los controles.
- La refracción y el brillo se calculan a partir del mismo campo de distancia, así el cristal sigue al borde sin coste extra apreciable.
- La zona que acepta clics sigue siendo el rectángulo interior estable, no la silueta que se mueve.
- En ventanas que duran mucho (Ajustes, instalador) el movimiento debería ser lento o activarse solo al interactuar, para no redibujar sin parar. Por decidir con el usuario.
- En las burbujas de texto, la misma animación con menos amplitud. El usuario lo dejó como posibilidad («igual también»): probarlo y que lo decida viéndolo.
- Ajuste para desactivar el movimiento. Con «reducir movimiento» de Windows, desactivado por defecto.

### 2.7 Blur gris: ¿merece la pena?

Opciones, de más a menos coste:

1. **Desenfoque en tiempo real** (nivel Medio): es lo mismo que el cristal sin refracción ni reflejos, así que no ahorra gran cosa frente al cristal completo.
2. **Desenfoque del compositor** (ruta A), si el prototipo demuestra que funciona sin foco: sería la opción barata y limpia.
3. **Esmerilado estático**: una sola captura al aparecer el panel, desenfocada una vez. Muy barato, pero se queda desfasado si lo de detrás cambia (un vídeo, por ejemplo).
4. **Tinte gris con grano y brillo** (ruta C): no mira lo de detrás; coste casi nulo.

Recomendación provisional: no decidir hasta medir. Si la ruta A funciona, el «blur gris» sería esa. Si no, ofrecer cristal (Alto), tinte (Bajo) y valorar el esmerilado estático como intermedio.

### 2.8 Privacidad

Si se usa la captura (ruta B), las imágenes **se quedan en la memoria de la GPU**: nunca se guardan en disco, no se envían y no pasan al núcleo ni al LLM. Debe quedar escrito en la SPEC (sección 8) y explicado en Ajustes, porque Nyx es local y privado por diseño.

### 2.9 Caso aparte: la ventana de Ajustes

Ajustes es la única ventana clásica, con foco. Ahí los materiales de Windows (Mica, Acrylic) sí funcionan y son casi gratis. Aun así, para que todo se vea igual, la idea es usar el motor propio también en Ajustes y en el instalador, y dejar los materiales de Windows solo como respaldo. Por confirmar al diseñar Ajustes.

## 3. Instalador propio

### 3.1 Lo que pidió el usuario

- Instalador **completamente personalizado**, **sin bordes** y con **todo el texto propio**, con el mismo estilo que la ventana de Ajustes.
- **Animaciones propias** mientras se descarga y se instala todo.
- Al terminar, la **onda de cristal** (apartado 4) sale del panel de instalación.

### 3.2 Viabilidad

Viable. Hoy no existe instalador. La SPEC prevé Velopack (secciones 2 y 15), cuya pantalla apenas se puede personalizar; el instalador de Tauri (NSIS/MSI) usa los diálogos clásicos de Windows.

**Propuesta:** un instalador propio, `NyxSetup.exe`, que sea una app Tauri pequeña con la misma tecnología que el resto de la interfaz:

- Ventana sin bordes y transparente, con los componentes Svelte de Ajustes y los fondos del motor gráfico.
- Por debajo lanza la instalación de Velopack **en modo silencioso** (hay que confirmar las opciones exactas), así se conservan las actualizaciones atómicas, los deltas y la vuelta atrás de la sección 15.
- Después descarga los modelos (lo más pesado) con progreso real y verificación SHA-256, reutilizando la lógica de `nyx --download-models`.
- Instalación por usuario (`%LOCALAPPDATA%`): sin permisos de administrador.
- WebView2 ya viene con Windows 11.

### 3.3 Límites que pone Windows

- El aviso de **SmartScreen** aparece antes de abrir el instalador mientras no haya firma (SignPath, fase 6). No se puede personalizar.
- La **desinstalación** desde Configuración de Windows usa la pantalla de Velopack. Se puede añadir un botón propio de desinstalar en Ajustes.
- Las **actualizaciones** siguen como en la sección 15 (avisos en la isla); no pasan por el instalador.

### 3.4 Por definir

- Pasos y textos del instalador (bienvenida, licencia GPL-3.0, permiso de datos anónimos de la sección 8, carpeta, micrófono, descarga, final).
- Las animaciones de descarga e instalación: el usuario aún no las ha descrito.
- Qué hacer si falla la descarga o se corta la luz a mitad (reanudar).

## 4. Onda de cristal e indicador de «Nyx listo»

### 4.1 Lo que pidió el usuario

- Animación final de la instalación: una **onda de cristal que sale del panel de instalación y recorre todos los monitores como si fueran uno solo**.
- La misma onda sirve de **indicador de que Nyx está listo** al encender el PC.
- **Se puede desactivar en Ajustes.**
- Alternativa en Ajustes: que **Nyx (el cuadrado blanco) aparezca y desaparezca**, para saber que está listo sin que una onda cruce todos los monitores.

### 4.2 Viabilidad

Viable, y depende del motor gráfico (ruta B: la onda deforma lo que hay detrás, así que necesita la captura).

**Propuesta:**

- Una ventana transparente **por monitor** (siempre encima, sin foco, deja pasar los clics), todas con el mismo reloj y dibujando su trozo de una onda definida en las coordenadas del escritorio virtual. Así se ve como un único lienzo aunque los monitores tengan distinta escala o disposición. Una sola ventana gigante se descarta por los problemas con escalas mezcladas.
- Las ventanas existen solo durante la animación (1–2 s) y se destruyen al acabar, para respetar la regla de la sección 11: en reposo no hay ninguna ventana visible.
- Origen de la onda: el panel del instalador, o la posición del indicador cuando es el aviso de «Nyx listo».
- La distancia física entre monitores no se conoce: la onda salta de uno a otro según las coordenadas de Windows.

### 4.3 Ajuste nuevo (Apariencia)

«Indicador de Nyx listo»: **Onda** · **Nyx aparece y desaparece** · **Nada**.

La onda no se muestra, y se usa el cuadrado en su lugar, si hay una partida, si Windows tiene «reducir movimiento», si el nivel de calidad es Bajo o si la captura no está disponible. El valor predeterminado está por decidir.

## 5. Secciones de la SPEC que habrá que actualizar al aprobarlo

| Sección | Cambio |
| --- | --- |
| 2 (stack) | «Efecto cristal»: motor propio en lugar de `window-vibrancy`. «Empaquetado»: instalador propio sobre Velopack. |
| 8 (privacidad) | La captura para el cristal no sale de la GPU. |
| 11 (overlay) | Cristal real en tiempo real, bordes líquidos, ventanas temporales de la onda. |
| 12 (identidad) | Fondos de cristal, silueta líquida de los paneles; «Cristal nativo» deja de ser «más adelante». |
| 13 (configuración) | Calidad del cristal, movimiento del borde, indicador de «Nyx listo». |
| 14 (rendimiento) | Objetivos de GPU del motor y bajadas automáticas de calidad. |
| 15 (actualizaciones) | El instalador propio lanza Velopack en silencio. |
| 16 (fases) | Dónde entran el motor, el instalador y la onda. |
| 18 (decisiones) | Registrar lo que se acuerde. |

## 6. Preguntas abiertas para el usuario

- ¿En qué fase entra el motor gráfico? Hoy está en curso la fase 5 (quedan 5b–5d, con el rediseño de los paneles) y el cristal nativo estaba previsto para después de la v1. Si los paneles nuevos van a usar el motor, convendría hacerlo antes de rediseñarlos.
- Valor predeterminado del indicador de «Nyx listo»: ¿onda o cuadrado?
- ¿El borde líquido se mueve siempre o solo al aparecer y al interactuar?
- ¿Borde líquido también en las burbujas de texto? (Decidir viéndolo en el prototipo.)
- Animaciones de la descarga y la instalación: faltan por describir.
- ¿Qué se queda como «blur gris»? Depende de las mediciones del prototipo (2.7).

## 7. Siguiente paso propuesto

Un prototipo del motor, corto y aislado (como la prueba de cristal de la fase 1), que conteste con mediciones en los dos equipos:

1. ¿Funciona la ruta A (compositor) en ventanas sin foco y con silueta animada sin escalones?
2. ¿Cuánta GPU y cuánto retraso tiene la ruta B con un panel del tamaño de una burbuja y con uno del tamaño de Ajustes?
3. ¿Cuánto añade el borde líquido?
4. ¿Cómo se compone la capa nativa con la WebView de Tauri?

Los resultados, en `docs/benchmarks/`, como el resto de las pruebas. Según las reglas de trabajo, antes hay que proponer el plan con los archivos y esperar el visto bueno.
