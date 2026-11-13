# Para revisar al volver

Trabajo hecho sin el usuario (desde el 2026-11-13, por la tarde). Cada punto dice qué probar y
qué decisiones quedan. Al revisarlo, lo que esté bien se borra de aquí; lo que no, se apunta en
`ERRORES.md` o se decide.

## Decisiones pendientes

1. ~~`run_powershell`, ¿excepción verde?~~ **Sí** (2026-11-13). Hecho: lista cerrada de consultas
   de solo lectura sin preguntar. Probar: «¿qué IP tengo?» (sin confirmación) y «¿qué hay en
   mi carpeta temporal con PowerShell?» (con confirmación: lee archivos).

2. **LoRA (6.27).** ~~Permiso para llama.cpp~~: dado el 2026-11-13. Ruta probada: la ronda 1
   ya está en Ollama como `nyx-r1:7b` (GGUF Q4_K_M, 4,7 GB, misma plantilla y parámetros que
   `qwen2.5:7b`). Pendiente: medirla en Ollama cuando acabe de entrenar la ronda 2 (no caben
   las dos cosas en la gráfica) y decidir con las dos rondas.

   **Ronda 1 medida, no se adopta** (`docs/benchmarks/lora-6.27.md`): acierta mucho más
   (reserva 50 → 72 de 80; batería 341 → 373 de 400) pero **actúa cuando no debe** («llama a
   mi hermano» → llamada de WhatsApp a un número inventado; «pídeme una pizza» → temporizador;
   «gracias, Nyx» → deshacer). Ronda 2 entrenando con lo que faltaba: cuándo **no** actuar.
   Tamaño: 970 ejemplos y una pasada (~4,5 h por ronda en la RX 7700 XT); más ejemplos o
   pasadas, de noche si hace falta.

3. **Buscar en internet (6.05).** El plan decía que eligieras tú. He hecho lo que no depende
   de esa elección: **Wikipedia** (gratis, sin clave) y **abrir la búsqueda en el navegador**.
   Pendiente: (a) si quieres actualidad (noticias, resultados), elegir una API con clave
   (Brave Search, Bing… con plan gratuito); (b) el buscador del navegador es **Google** por
   defecto (`web.search_url`): dime si prefieres otro (DuckDuckGo, Bing…).

4. **6.07 (aprender recetas), sin empezar.** Necesita dos cosas que no puedo decidir bien solo:
   (a) un buscador de webs de verdad para los «cómo se hace» (Wikipedia no los tiene: va con
   la decisión 3a); y (b) cambiar el prompt de sistema para que el modelo ofrezca «¿lo busco?»,
   que conviene hacer **después** de decidir si el LoRA se queda (se entrena con el prompt
   actual y cambiarlo ahora lo desajustaría). Alternativa sin internet: que el modelo proponga
   la receta con lo que ya sabe (pasos con las herramientas que hay, cada uno confirmado).

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
