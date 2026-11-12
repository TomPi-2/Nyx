# Coste de los grupos · qwen2.5:7b · num_ctx 12288

- Todas las herramientas (39): **5251** tokens de prefijo; primer token en caché 0.07 s, al volver a ellas desde un grupo 2.29 s.
- Solo las fijas (6): **1455** tokens; en caché 0.03 s.
- Cambio de grupo: mediana **0.26 s**, peor 0.49 s.

| Grupo | Herramientas | Tokens sobre las fijas | Primer token al cambiar | En caché |
| --- | --- | --- | --- | --- |
| ventanas | 3 | 239 | 0.23 s | 0.04 s |
| teclado | 3 | 417 | 0.26 s | 0.06 s |
| archivos | 4 | 526 | 0.32 s | 0.03 s |
| archivos_cambiar | 4 | 779 | 0.49 s | 0.07 s |
| alarmas | 5 | 459 | 0.31 s | 0.03 s |
| equipo | 5 | 494 | 0.34 s | 0.03 s |
| configuracion | 2 | 157 | 0.16 s | 0.06 s |
| musica | 1 | 52 | 0.10 s | 0.03 s |
| nyx | 4 | 470 | 0.32 s | 0.03 s |
| clima | 1 | 85 | 0.15 s | 0.03 s |
| portapapeles | 1 | 118 | 0.13 s | 0.03 s |

`scripts/groups_bench.py`, PC de referencia (RX 7700 XT), 2026-11-12. Las fijas son
`open_app`, `close_app`, `open_url`, `set_volume`, `media_control` y `undo`.

## Batería de 337 frases con cada modo (`scripts/battery.py`, 3 pasadas por frase del LLM)

| Modo | Acierto | LLM | Primer token (1.ª pasada): mediana / media |
| --- | --- | --- | --- |
| Línea base 6.17: todas, orden del archivo | 256/337 | 110/185 | — |
| Todas, frases desordenadas (`--sin-grupos --mezclar 1`) | 257/337 | 111/185 | 362 / 370 ms |
| Fijas + grupo del tema, orden del archivo (primer diseño) | 255/337 | 109/185 | 347 / 417 ms |
| Fijas + grupo del tema, desordenadas (primer diseño) | 254/337 | 108/185 | 490 / 532 ms |
| **Diseño final con 12.288 (caben todas): lo que usa Nyx** | **258/337** | **112/185** | **350 / 358 ms** |
| Diseño final con 8.192 (`--contexto 8192 --mezclar 1`: grupos rotando) | 244/337 | 98/185 | 353 / 481 ms |

## Qué dice

- **Recortar la lista no ayuda al 7B, le perjudica.** Con el primer diseño (cada petición:
  fijas + el grupo del tema) el acierto es el mismo (arregla ~12 frases y rompe otras ~13), y
  con los grupos rotando por falta de sitio baja 14 frases en lo que llega al LLM. Con menos
  herramientas a la vista, el modelo escribe más la orden como texto («abre Paint», «activa
  el wifi», «pon el brillo al 100») en vez de llamar a la herramienta.
- **Cada cambio de grupo cuesta tiempo:** 0,1–0,5 s (mediana 0,26 s). En uso real (temas
  mezclados), el primer diseño subía la media del primer token ~160 ms.
- **Volver a la lista entera desde un grupo cuesta 2,3 s**: mezclar los dos modos sería lo
  peor.
- El selector por palabras acierta el grupo en 295 de 296 frases con herramienta (la que
  falta pide reconocer el nombre de una carpeta concreta).

## Decisión (diseño final de la 6.20b)

- Las herramientas pueden ocupar como mucho el **40 % del contexto**
  (`select.tools_budget`). Mientras quepan todas, el modelo las ve todas y en el mismo orden:
  hoy, con 39 herramientas y 12.288 de contexto, Nyx se comporta y tarda como antes.
- Cuando no quepan (extensiones de la 0.7), los grupos funcionan como una caché: fijas +
  grupos usados hace poco, el nuevo al final y fuera el más antiguo. Probado con 200
  herramientas falsas en 40 grupos (`tests/test_select.py`): el prompt no pasa del
  presupuesto y elegir cuesta < 5 ms.
- **6.20d (bajar el contexto a 8.192) no compensa hoy:** ahorraría ~235 MB de VRAM pero
  costaría 14 frases y ~120 ms de media. Los FPS que se pierden mientras piensa vienen del
  cálculo de la gráfica, no de la memoria; solo tendría sentido si en tarjetas de 8 GB la
  VRAM se queda corta en partida.
- Para que las extensiones no bajen el acierto, antes hay que arreglar el «no actúa» (el
  fallo principal de la 6.17), que con la lista recortada empeora.
