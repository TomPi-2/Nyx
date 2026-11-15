# Para revisar al volver

Trabajo hecho sin el usuario (desde el 2026-11-13, por la tarde). Cada punto dice qué probar y
qué decisiones quedan. Al revisarlo, lo que esté bien se borra de aquí; lo que no, se apunta en
`ERRORES.md` o se decide.

## Decisiones pendientes

1. ~~`run_powershell`, ¿excepción verde?~~ **Sí** (2026-11-13). Hecho: lista cerrada de consultas
   de solo lectura sin preguntar. Probar: «¿qué IP tengo?» (sin confirmación) y «¿qué hay en
   mi carpeta temporal con PowerShell?» (con confirmación: lee archivos).

2. ~~LoRA (6.27): ¿se adopta la ronda 2?~~ **Sí, opción a)** (2026-11-13). Tu Nyx ya usa
   `nyx-r2:7b` (`llm.model` en `settings.json`; la copia anterior, en
   `settings.json.antes-nyx-r2`). Reinicia el núcleo para que lo coja. Pendiente: medirla en
   partida (`game_bench.py`) y llevar el GGUF al portátil si se usa allí.

   **Ronda 3 (`nyx-r3:7b`, ya en Ollama): ¿se cambia a ella?** Detalle en
   `docs/benchmarks/lora-6.27.md`, «Resultado de la ronda 3». Batería 392/409 (+1) y reserva
   73/80 (+3); arregla 6 de los 8 fallos de la r2 y «no actúa» baja de 10 a 5. Pero rompe 7
   (4 son llamadas mal formadas que Nyx reintenta), **actúa sin deber una vez** («¿qué hora
   será en Nueva York?» → el tiempo; inofensivo) y en «apaga el wifi y bloquea el ordenador»
   pide **apagar** en vez de bloquear (rojo: Nyx pediría confirmación). Mi recomendación:
   **quedarse con la r2** hasta una ronda 4 que corrija eso, porque lo de «bloquear → apagar»
   es justo el tipo de error que no queremos aunque esté protegido. Para cambiar: `llm.model`
   = `nyx-r3:7b` en `settings.json`.
   Latencia medida igual para los tres (un solo modelo cargado): base 231 ms, r2 350 ms, r3
   360 ms de mediana hasta la primera palabra; todos muy por debajo de 1,5 s.

3. ~~Buscar en internet~~ **Decidido** (2026-11-13): sin pagar ninguna API. Hecho: búsqueda en
   segundo plano con DuckDuckGo, leyendo las 2 mejores páginas (o Wikipedia si DuckDuckGo
   falla), y Google para abrir en el navegador. Probar: «busca cómo poner la barra de tareas a
   la izquierda», «busca una receta de lentejas con chorizo». **Ojo:** DuckDuckGo no es un
   servicio oficial para programas; revisarlo antes de la beta (0.9).

4. ~~6.07 sin «¿Lo busco?»~~ **Confirmado** (2026-11-13): lo que queda pasa a la 0.7.

5. ~~Publicar el repositorio~~ **Adelante** (2026-11-13). Hecho: «GPL-3.0-only» en todo (el
   núcleo ya lo declara), `nyx-v1.onnx` y `nyx-v1.pt` bajo CC BY-SA 4.0 con sus atribuciones
   (`core/nyx/wake/data/LICENSE-nyx-v1.md`), borradores de CLA, SECURITY y CONTRIBUTING
   aceptados (el CLA, mejor que lo mire también el abogado). Créditos en la app: 0.9.
   **Falta que confirmes dos cosas, porque no tienen vuelta atrás:**
   - **Tu correo en el historial** (y el usuario de Windows en 5 líneas antiguas): no te di
     recomendación. Reescribir el historial lo oculta, pero cambia el identificador de todos
     los commits (los del Registro de los planes dejarían de valer y habría que rehacerlos) y
     obliga a forzar la subida a GitHub. Mi recomendación ahora: **reescribirlo**, una sola
     vez y justo antes de publicar, porque después ya no se puede quitar; y desde hoy, el
     correo `noreply` de GitHub en los commits nuevos. ¿Lo hago?
   - **Hacer público el repositorio** (y SignPath): lo hago cuando me digas «publícalo»,
     después de lo del correo.

6. ~~Contrato de voz~~ **Hecho** (2026-11-13): lo revisa un abogado. Abierto: la ciudad
   (te propuse Valencia como lugar de celebración y los juzgados del domicilio de quien sea
   demandado).

7. ~~Plan de la 0.7~~ **Aprobado** (2026-11-13): se empieza al cerrar la 0.6.

8. ~~¿Quién ha creado a Nyx?~~ **Tepnyx** (2026-11-14). Hecho, junto con todo Tepnyx (ver
   «Qué probar», 10).

9. ~~0.7, aislamiento (7.05)~~ **Aprobado** (2026-11-14). Hecha la 7.06: cada extensión con
   código corre en su AppContainer, en su escritorio y con límites, y habla con Nyx por su
   entrada y salida. Probado con una extensión que intenta leer tus archivos, conectarse,
   lanzar `cmd`, ver variables y pasarse de memoria: no puede. **Decidido por mí (a
   confirmar):** el Python de las extensiones es el 3.14.10 (la 3.12, la del núcleo, ya no
   publica binarios con parches); las extensiones traen sus dependencias para esa versión.

10. ~~Firma (7.08)~~ **Confirmada** (2026-11-14). Tu clave `tepnyx-1` ya está en `TRUSTED_KEYS`
    (venía sin el id; corregido y comprobado que casa con tu clave privada). La privada está
    ahora en `%LOCALAPPDATA%\Tepnyx\keys\` (Local no viaja con el perfil; la he movido desde
    Roaming). **Haz una copia fuera del PC** (un USB o tu gestor de contraseñas): si se pierde,
    hay que sacar una versión de Nyx con una clave nueva.

12. ~~Modo Noche (7.10)~~ **Confirmado** (2026-11-14): abre Configuración. No hay forma oficial;
    la no oficial (escribir un dato binario sin documentar del registro) funciona hoy en muchas
    versiones pero Windows ya la ha cambiado otras veces. Lo automático de verdad lo trae
    Windows: «Programar luz nocturna» (del atardecer al amanecer), y Nyx puede decirte dónde.

13. ~~Licencia del kit (7.12)~~ **MIT, sí** (2026-11-14). Hecho: `manifest.py`, `content.py` y
    `signing.py` llevan `GPL-3.0-only OR MIT` (`docs/LICENCIAS.md`).

14. ~~Extensiones de pago~~ **Siempre de pago único** (2026-11-14), de Tepnyx y de terceros:
    apuntado en HOJA-DE-RUTA §8.3. El manifiesto ya admite `"license": {"type": "paid",
    "product": …}` y la compra se demostrará con una licencia firmada que Nyx comprueba sin red
    (ya previsto). Queda para la 1.1: si la compra incluye las versiones mayores futuras.

15. ~~Primer arranque guiado por Nyx (9.10)~~ **Aprobado** (2026-11-14), con el plan de
    construcción (`docs/PLAN-0.9.md` §1b) y el paso del núcleo a Python 3.14 al empaquetarlo
    (9.07). **Hecha la 9.10a** (ver «Qué probar», punto 12).
16. **Núcleo empaquetado (9.07), hecho sin ti el 2026-11-14.** El núcleo ya va en Python 3.14
    (también tu `core\.venv`: `uv run` lo usa sin más) y se empaqueta con su propio Python.
    Para que lo decidas o lo sepas:
    - **Ocupa 1.010 MB**, casi todo PyTorch (lo necesita la voz de Pocket TTS). Se podría
      bajar (PyTorch recortado o la voz en ONNX), pero no lo he tocado: ¿lo miro más adelante?
    - El código del núcleo va como .pyc **y** .py (GPL: el código tiene que poder verse). Si
      prefieres solo .pyc en el instalador, se cambia en una línea.
    - Descarté Nuitka y PyInstaller (la SPEC los nombraba): con PyTorch, ONNX y pywin32 dan
      más guerra, y el Python embeddable es el mismo de las extensiones. Ya está en la SPEC.

17. **Actualizaciones (9.06), hecho sin ti el 2026-11-14.** Lo que no he podido o no he
    querido decidir solo:
    - **Vuelta atrás automática** (SPEC §15, paso 6): Velopack no la trae. Propuesta: antes de
      aplicar, guardar el paquete de la versión actual; si la nueva no arranca en 60 s o el
      núcleo se cae 3 veces seguidas, reaplicarlo y avisar. ¿Lo hago?
    - **«Más tarde»** vuelve a preguntar a las 4 h y, si cierras Nyx o apagas antes, se
      aplica al volver a abrirla (no justo al apagar: Windows no da tiempo de forma fiable).
    - **«Solo avisar»** tiene el botón [Actualizar]; falta decirlo por voz («Nyx,
      actualízate»). ¿Lo añado?
    - Probarlo de verdad necesita el repositorio público y una Release firmada (9.09).
18. **Instalador (9.08), hecho sin ti el 2026-11-14.** Decidido con lo que había; dime si no:
    - **Carpeta:** `%LOCALAPPDATA%\TepnyxNyx` (identificador de Velopack `TepnyxNyx`). No
      `%LOCALAPPDATA%\Nyx`: ahí están tus datos y modelos, y al desinstalar Velopack borra su
      carpeta entera. Los datos se quedan al desinstalar.
    - **Ollama** se instala con winget (como Everything): oficial, comprobado y sin
      administrador. Lo hace el panel de descargas de Nyx (como en el prototipo), no el
      instalador. Si no hay winget, lo dice y no se instala.
    - **Quité «Cambiar carpeta»** de Opciones (Velopack instala siempre en la carpeta del
      usuario). ¿Lo quieres?
    - **«Arrancar con Windows»** viene encendido y lo pone el instalador; aún no hay un
      interruptor en Ajustes para quitarlo. ¿Lo añado en General?
    - ~~El cristal del instalador, el de CSS~~ **Hecho tras tu prueba:** el del motor (si la
      gráfica puede, con el borde moviéndose siempre) y la forma real de Nyx, sin girar,
      llenándose con el porcentaje.
    - **whisper-server** para publicar tiene que ser el compilado sin `GGML_NATIVE` (con las
      variantes de CPU): el de `C:\dev\tools` ahora mismo solo trae `ggml-cpu.dll`, que es el
      que se caía en el portátil.
    - ~~Versión~~ **0.9.0, beta** (tu decisión, 2026-11-14): ya en el código.
    - Sin firma, SmartScreen avisará al abrir «Instalar Nyx.exe» (SignPath en la 9.09).
    - **El fallo de tu prueba:** Nyx sí se instaló (dos veces; `velopack.log` dice «completed
      successfully»), pero el instalador buscaba `nyx-ui.exe` y Velopack deja `Nyx.exe`. Ya
      corregido. Te ha quedado instalada en `%LOCALAPPDATA%\TepnyxNyx` con un acceso directo
      en el escritorio que puso Velopack por su cuenta (ya no lo hará). Al instalar la nueva
      encima se arregla; o desinstálala desde Configuración → Aplicaciones (tus datos se
      quedan).
    - ~~Códigos de error~~ **Decidido** (2026-11-15): la página de errores irá en la web de
      Tepnyx junto con la de Nyx, y se harán al final (apuntado en CLAUDE.md, antes de
      publicar). Recompilar `whisper-server`: también en esa lista, para recordártelo.

## Qué probar

Probado y bien (2026-11-13): color de Nyx (6.23), ciudad automática (6.24) y falsas
activaciones (6.22).

2. **Paneles (6.23):** unas preguntas por voz y escritas. Mayúscula al principio, punto solo en
   las frases, la línea pequeña solo si aporta, y un «Sí» suelto cambiado por la frase.
3. **Respuestas con variedad (6.26):** «¿cuánta batería me queda?», «¿qué suena?», «¿cuánto
   marca el crono?» varias veces y con cada tono (se aplica al reiniciar).
6. **Reglas nuevas (6.25):** frases como «necesito la calculadora», «pon el Chrome en grande»,
   «la pasta tarda 12 minutos, avísame», «me deslumbra la pantalla», «vivo en Sevilla»…
   (todas en `docs/benchmarks/bateria-6.25-*.md`).
7. **Respuestas largas y notas (6.28)** (reinicia el núcleo y la interfaz: protocolo v17):
   - Por voz: «Nyx, explícame por qué el cielo es azul». El panel se escribe letra a letra al
     ritmo de la voz, sin borrar; sube con la rueda mientras habla («Seguir leyendo»). Corta a
     Nyx a mitad («Nyx, ciérralo»): la voz para y el panel se cierra (no cierra ninguna app).
   - «Nyx, busca una receta de tortilla de patatas»: panel con Ingredientes y Pasos, la voz
     dice un resumen y «¿Te la guardo en una nota?». Di «sí»: se abre el Bloc de notas con la
     receta (en `Documentos\Notas de Nyx`). Prueba «Deshacer» (a la papelera; vuelven los
     botones), «cópiala», «cierra el panel».
   - Escrito (Win+Alt+N): una pregunta larga sale de golpe en el panel largo.
   - «Apunta en una nota que mañana tengo dentista»: nota nueva al momento.
   - Lo que no he podido probar sin ti: la interfaz real (cristal, tamaño de la ventana, la
     rueda y el puntero encima), la voz real sincronizada y el tiempo de la estructura con el
     7B (2–4 s más tras buscar una receta).

8. **Revisión de cierre (6.19)** (reinicia el núcleo):
   - Con una receta o explicación en pantalla y música sonando, «Nyx, pásala»: pasa la canción
     y el panel sigue. «Pásala a una nota» sí la guarda.
   - «¿Qué IP tengo?» sigue sin preguntar; algo como «dime la carpeta de mi usuario con
     PowerShell» (usa `$env:USERPROFILE`) ahora pide confirmación.
   - Buscar en internet funciona igual (no debería notarse nada).

9. **Arreglos tras tu prueba del 2026-11-14** (reinicia el núcleo):
   - Unas cuantas preguntas de charla seguidas («cuéntame un chiste», «¿cómo hace la vaca?»):
     el panel dice algo que tiene que ver, nunca «Noche».
   - «¿Cuál es mi IP?»: tu IP local real, al momento y sin preguntar.
   - Justo después de una respuesta, «Nix, ¿quién es tu creador?» se atiende (antes se
     ignoraba). «Esto está roto. Nyx, ¿qué día es hoy?» contesta al día.
   - «Vale, ábreme Netflix» lo abre.
   - Nyx aprendió un atajo de una frase mal oída: «po muusiga» → abrir la web «Spotify» (que no
     existe). Bórralo en Ajustes → Cerebro → Atajos aprendidos («Olvidar»).

10. **Tepnyx** (reinicia el núcleo y en Ajustes → Caché, «Volver a escanear», para que conozca
    las páginas): «¿quién te ha creado?» (dice «Me ha creado Tepnyx»), «¿qué es Decider Bot?»,
    «¿qué apps tiene Tepnyx?», «abre la ruleta de sí o no», «abre Tepnyx Premium», «¿dónde
    cambio tu voz?» (Ajustes en Voz). Decider y Sorty son apps del móvil: en el PC Nyx abre su
    página. Si echas en falta alguna pantalla o página, dímela.

12. **Primer arranque guiado de verdad (9.10a)** (reinicia la app entera: protocolo **v20**).
    Ajustes → Ayuda → Primer arranque → «Repetir». Nyx aparece, te habla y saca debajo un panel
    por paso: micrófono (y por dónde suena), color («ponte coral»), tamaño («más pequeño» o
    arrastrando), paneles, escaneo y datos. **Tras tu primera prueba:** ya no se activa con su
    propia voz; te escucha sin «Nyx» todo el rato desde la bienvenida (di «empezar»,
    «siguiente»… cuando acabe de hablar, sin prisa); para cortarla mientras habla, «Nyx,
    siguiente». Pulsa «Siguiente» mientras habla: debe callarse en un instante. Cambia tu color
    y tamaño de verdad. El panel de descargas solo sale si falta algo.

13. **La onda de «Nyx lista» (9.04)**: Ajustes → Apariencia → «Al estar lista» → «Probar».
    Debe salir una onda de cristal desde el sitio de Nyx que deforma lo que hay detrás y cruza
    tus dos monitores como si fueran uno (según cómo los tengas colocados en Windows), en
    ~1,7 s, sin quitarte el foco ni bloquear el ratón. Con «Nyx aparece y desaparece», Nyx sale
    un momento. También sale al arrancar Nyx y al acabar el primer arranque. En partida, con
    «reducir movimiento» o con el cristal en Bajo, sale Nyx en vez de la onda. Dime si la
    quieres más lenta, más gruesa o con más brillo.

11. **Prototipos para tu visto bueno** (ábrelos en el navegador):
    - `docs/prototipos/instalador.html`: el instalador entero y la onda de «Nyx listo» cruzando
      dos monitores. Prueba «Cortar la red» y «"Nyx listo" al encender». ¿Te gustan los pasos,
      la forma de Nyx que se llena y la onda? Hasta que digas, no lo construyo de verdad.
    - `docs/prototipos/extensiones.html`: Ajustes → Extensiones. Pulsa en cada extensión, prueba
      «Instalar una firmada» e «Instalar sin firma» (con el modo desarrollador apagado y
      encendido) y la actualización que pide un permiso nuevo.

## Hecho en esta tanda

- **6.13 `run_powershell`** (roja siempre, bloqueada en partida). La lista de bloqueo usa el
  analizador de PowerShell, no el texto: borrar sin papelera, sobrescribir archivos (`>`,
  `Set-Content`, `-Force`), discos, registro, políticas, servicios, desinstalar, descargar o
  ejecutar código de fuera, elevarse, apagar, otros intérpretes y `& $x`. Si el análisis falla,
  no se ejecuta. Probar: «¿qué IP tengo?» (debe pedir confirmación con el comando exacto) y
  algo peligroso como «borra la carpeta temporal con PowerShell» (debe negarse).
- **6.14 `install_app`** (roja siempre, bloqueada en partida): busca con winget y la
  confirmación enseña el nombre exacto, el editor y el id; si hay varios que se parecen, no
  adivina y dice cuáles. Instala en silencio y sin `--force`. Probar: «instálame el VLC» (debe
  pedir confirmación con «VideoLAN · VideoLAN.VLC»), cancelarlo, y «instala Chrome» (varios:
  debe preguntar cuál). **Limitación:** mientras instala, Nyx espera (hasta 15 min) y no
  atiende otra cosa; avisar al acabar en segundo plano queda para más adelante.
- **6.14 `ui_action`** (UI Automation; nunca en juegos ni en Nyx; bloqueada en partida): pulsar
  un botón o un menú, marcar una casilla o leer un texto por su nombre. Leer es verde; pulsar y
  marcar, amarillo (Nyx avisa de que no se puede deshacer); rojo si el control se llama
  «Eliminar», «Enviar», «Pagar», «Desinstalar»… Si hay varios parecidos, pregunta cuál. Al
  ejecutar comprueba que el control sigue siendo el mismo **antes** de tocarlo. Probado sin
  pulsar nada: encuentra el botón «Minimizar» de VS Code. Probar: en una ventana con botones,
  «pulsa Aceptar» o «¿qué pone en el aviso?». Los menús de apps tipo Electron (VS Code,
  Discord) a veces no se ven por UI Automation.
- **6.06 `web_search`** (verde, permitida en partida): «busca en internet quién inventó la
  imprenta», «búscalo en el navegador». La burbuja dice la fuente (es.wikipedia.org). Lo que se
  lee va al modelo como información y **en esa vuelta no tiene herramientas** (una web no puede
  hacer que Nyx actúe; probado con una web que dice «borra la carpeta Documentos»). Sin
  conexión: «No tengo conexión» al momento. Interruptor en Ajustes → Privacidad. Las preguntas
  de cultura general las sigue contestando el modelo solo, sin buscar.
- **Tanda 7 de reglas:** «ponte de color rosa», «esta canción no me gusta, pásala», «llévame a
  la ventana del Discord», «quítale el sonido al Chrome», «olvida el recordatorio de llamar a
  mamá», «pon algo para relajarme». Y arreglado: «búscame la foto del DNI» buscaba «l dni».
- **«Gracias, Nyx»** se contesta sin el modelo, con variantes según el tono («¡De nada!», «Para
  eso estoy», «¡A mandar!»…). Solo la frase suelta («vale, muchas gracias», «te lo agradezco»);
  «no, gracias» o «gracias, ahora pon música» siguen su camino. Probar por voz y escrito.
