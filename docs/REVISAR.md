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
   `settings.json.antes-nyx-r2`). Reinicia el núcleo para que lo coja. Ronda 3 entrenando
   (~4 h; mientras, Nyx no puede usar la gráfica) con frases nuevas para los 8 fallos
   (`core/training/llm/fixes.py`). Pendiente: medirla en partida (`game_bench.py`) y llevar el
   GGUF al portátil si se usa allí.

3. ~~Buscar en internet~~ **Decidido** (2026-11-13): sin pagar ninguna API. Hecho: búsqueda en
   segundo plano con DuckDuckGo, leyendo las 2 mejores páginas (o Wikipedia si DuckDuckGo
   falla), y Google para abrir en el navegador. Probar: «busca cómo poner la barra de tareas a
   la izquierda», «busca una receta de lentejas con chorizo». **Ojo:** DuckDuckGo no es un
   servicio oficial para programas; revisarlo antes de la beta (0.9).

4. ~~6.07 sin «¿Lo busco?»~~ **Confirmado** (2026-11-13): lo que queda pasa a la 0.7.

5. **Publicar el repositorio** (auditoría completa en `docs/LICENCIAS.md`; todo compatible):
   - **GPL-3.0-only o -or-later.** La interfaz dice «only»; el núcleo no lo declara.
   - **Tu correo en el historial** (170 commits): dejarlo, o reescribir el historial antes de
     publicar para usar el correo `noreply` de GitHub (cambia todos los commits).
   - **Revisar los borradores** `CLA.md` (con alguien con criterio legal), `SECURITY.md`
     (avisos por el sistema privado de GitHub, sin correo) y `CONTRIBUTING.md`.
   - **`nyx-v1.onnx`** bajo CC BY-SA 4.0 por sus datos de entrenamiento (recomendado).
   - **Voz contratada:** fuera del repositorio, descargable aparte con su licencia. Para el
     contrato: autorizar el entrenamiento del modelo de voz dentro del proyecto, regular la
     revocación (LO 1/1982 art. 2.3) y definir «ingresos brutos».
   - Créditos en la app (Kyutai, OpenSLR, Open-Meteo, OpenStreetMap…): tarea para la 0.9.

6. **Contrato de voz** (2026-11-13): en Word, fuera del repositorio (lleva datos personales), en
   `Documentos\Tepnyx\Legal\`: `Contrato-cesion-voz-Nyx.docx` (listo para rellenar y firmar)
   y `Notas-revision-contrato-voz.docx` (qué se decidió, qué se corrigió y qué mirar con el
   abogado). Las 7 casillas que marcaste, aplicadas como proponía. Lo que decidí yo y puedes
   cambiar:
   - **Tope de la indemnización por revocación: 500 €** (o lo cobrado por el Cedente, si es
     más; nunca más de lo gastado de verdad). La cifra la puse yo.
   - **Ingresos mixtos de Tepnyx** (un patrocinio de toda la marca, vender varias apps juntas):
     a partes iguales entre los productos incluidos, salvo acuerdo. Hacía falta porque Tepnyx
     también es la marca de Decider: tal como estaba, sus ingresos contaban para el 10 %.
   - **Directos y vídeos**: la licencia de la voz ahora deja que se oiga en grabaciones y
     directos usando Nyx con normalidad (antes lo prohibía, y choca con «Mostrar Nyx en
     capturas y directos»).
   - **Logo**: no había ningún PNG de la bola en negro; lo saqué del blanco sin fondo
     (`Legal\tepnyx-mark-black.png`, la misma forma en negro puro).
   - Faltan: la ciudad de los juzgados y los datos de ambos. El documento de Claude del
     contrato se queda en la versión anterior: la buena es la del Word.

7. **Plan de la 0.7 (borrador):** `docs/PLAN-0.7.md`, 17 tareas sacadas de la hoja de ruta
   (§2, §4 y §5), con el mismo formato que el de la 0.6. No se empieza hasta que lo apruebes y
   cierres la 0.6. Decisiones que trae marcadas: cómo se aíslan las extensiones (7.05, se
   mide antes), dónde vive la clave de firma (7.08), luz nocturna y «no molestar» sin API
   oficial (7.10) y si Spotify deja «poner algo concreto» sin cuenta de desarrollador (7.14).

## Qué probar

1. **Color de Nyx (6.23):** Ajustes → Apariencia → un color que no sea blanco. Todo el cuadrado
   del mismo color, sin triángulos ni borde oscuro; el movimiento, igual que siempre.
2. **Paneles (6.23):** unas preguntas por voz y escritas. Mayúscula al principio, punto solo en
   las frases, la línea pequeña solo si aporta, y un «Sí» suelto cambiado por la frase.
3. **Respuestas con variedad (6.26):** «¿cuánta batería me queda?», «¿qué suena?», «¿cuánto
   marca el crono?» varias veces y con cada tono (se aplica al reiniciar).
4. **Ciudad automática (6.24):** con la ciudad vacía en Ajustes → General, «¿qué tiempo hace?».
5. **Falsas activaciones (6.22):** si salta sola varias veces, que deje de hacerlo un rato; el
   registro dice «Umbral de activación: 0.xx → 0.yy». Opción nueva en Ajustes → Activación.
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
