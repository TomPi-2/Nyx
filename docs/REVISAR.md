# Para revisar al volver

Trabajo hecho sin el usuario (desde el 2026-11-13, por la tarde). Cada punto dice qué probar y
qué decisiones quedan. Al revisarlo, lo que esté bien se borra de aquí; lo que no, se apunta en
`ERRORES.md` o se decide.

## Decisiones pendientes

1. **`run_powershell`, ¿excepción verde para órdenes de solo lectura?** El plan de la 0.6
   (6.13) proponía que órdenes como `Get-Date` o `Get-Process` se ejecutaran sin preguntar,
   pero la SPEC §7 dice «rojo siempre» y CLAUDE.md prohíbe bajar los niveles de seguridad. La
   he dejado **roja siempre** (cada comando pide confirmación). Si quieres la excepción, hay
   que cambiar la SPEC primero.

2. **LoRA (6.27), cuánto entrenar.** Cada ejemplo lleva el prompt y las ~42 herramientas
   (~6.800 tokens) y la RX 7700 XT con ROCm en Windows va a ~20 s por ejemplo: 2.000 ejemplos
   serían 12 h por pasada. He entrenado con **970 ejemplos y una pasada (~5-6 h)**, eligiendo
   lo que más vale (paráfrasis que las reglas no cogen, herramientas inventadas y algo de
   charla). Si el resultado promete, se puede entrenar más de noche. El LoRA se entrenó con
   las 42 herramientas de antes de `web_search` (una herramienta de diferencia: apenas cambia).

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
