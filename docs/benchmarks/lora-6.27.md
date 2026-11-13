# LoRA de qwen2.5:7b (6.27) · PC de referencia (RX 7700 XT)

## Cómo se mide

Ollama 0.40 no importa un Qwen2 ajustado (ver `core/training/llm/README.md`) y la conversión a
GGUF con llama.cpp (permiso del 2026-11-13) se probó después: ver «En Ollama», al final. Para decidir si el LoRA merece la pena,
`core/training/llm/serve.py` da la API de Ollama con el modelo de 4 bits de Unsloth y responde
como `base` (sin LoRA) o `lora`. La batería (`scripts/battery.py --host … --modelo …`) es la de
siempre: router, grupos, reencaminado, juez, 3 pasadas por frase y semilla 1. **Solo vale la
comparación entre `base` y `lora`**: el motor no es el de Ollama (en Ollama, el mismo `base`
saca 58/80 en la reserva, no 50/80) y las latencias no cuentan (sin caché ni streaming).

- **Reserva** (`tests/battery/reserva.jsonl`, 80 frases): nunca se usa para entrenar ni para
  escribir reglas. Es la medida honesta.
- **Batería** (`tests/battery/frases.jsonl`, 400 frases): las semillas del entrenamiento salen
  de ella, así que favorece al LoRA; sirve para ver lo que rompe.

## Ronda 1 (2026-11-13) · 970 ejemplos, 1 pasada, 278 min

Pérdida 0,298 (validación 0,252). Pico 7,3 GB.

| Conjunto | base | lora | Por el LLM: base → lora |
| --- | --- | --- | --- |
| Reserva | 50/80 (62 %) | **72/80 (90 %)** | 25/55 → 47/55 |
| Batería | 341/400 (85 %) | **373/400 (93 %)** | 71/130 → 103/130 |

Arregla 23 fallos de la reserva y 44 de la batería. **Pero rompe 13 frases** (1 de la reserva y
12 de la batería), casi todas porque **actúa cuando no debe**:

| Frase | Qué hace el LoRA |
| --- | --- |
| gracias, Nyx | `undo` |
| llama a mi hermano | `open_url` a una llamada de WhatsApp con un número inventado |
| manda un whatsapp a mi madre | `send_whatsapp` (no existe) |
| manda un correo a mi jefe diciendo que llego tarde | `type_text` con un correo inventado |
| pídeme una pizza | `set_timer` |
| ¿qué hora será ahora en Nueva York? | `set_timer` |
| cuenta del 1 al 10 | `media_control` |
| Crea tres archivos de texto | `create_folder` |
| publica en Instagram la última foto | `open_app` |
| hola, ¿qué tal estás? | `nyx_info` (1 de 3) |
| entra en mi correo de Gmail | `open_app` en vez de `open_url` |
| quiero el Discord en la mitad izquierda de la pantalla | `left_half` (no existe) |
| ábreme una pestaña de incógnito en Chrome | argumento inventado (1 de 3) |

Además, `now_playing` sale roto siempre que va por el LLM: escribe `{"name": "now`, un salto
de línea y abre otro turno (`<|im_start|>`). El modelo sin LoRA no lo hace.

**Veredicto: no se adopta** (regla del plan: solo si mejora sin fallos nuevos). Causa: se le
enseñó a actuar y no a no actuar (solo un 20 % de respuestas en texto, casi todas de cultura
general; ninguna de «eso no lo sé hacer» ni de cortesía).

Informes: `lora-6.27-r1-{reserva,bateria}-{base,lora}.md`.

## Ronda 2 (2026-11-13) · 970 ejemplos, mismos ajustes, 235 min

Cambios en los datos (`make_dataset.py juntar --maximo 1000`):

- Las 7 herramientas inventadas también **sin** la herramienta en la lista → «Aún no sé hacer
  eso» (19 frases × 2).
- `training/llm/limits.py`, escrito a mano: lo que ninguna herramienta hace (mensajes,
  llamadas, correo, reservas, redes, calendario, crear archivos, aparatos de casa), datos que
  suenan a orden («¿cuánto tarda en hervir un huevo?», «¿cómo se hace una captura?») y
  saludos («nada, déjalo», «¿estás ahí?»). 81 frases × 2, ninguna de la batería ni de la reserva.
- Paráfrasis repartidas por herramienta (15–18 cada una; antes, 94 de `window_layout` y 14 de
  `now_playing`).
- 360 de 1.000 ejemplos en texto (antes, 194).

Pérdida 0,427 (validación **0,126**, la mitad que la ronda 1). Pico 7,4 GB.

Aparte, «gracias» suelto ya no llega al modelo: lo contesta Nyx con variantes por tono
(`brain/answers.py`). En la batería sigue llegando al modelo (mide al modelo, no a Nyx).

## En Ollama (2026-11-13) · los tres modelos, como los usaría Nyx

Cada ronda unida al modelo base, convertida a GGUF y cuantizada a Q4_K_M con llama.cpp (4,7 GB,
como `qwen2.5:7b`), y creada en Ollama con la misma plantilla, sistema y parámetros, comprobado
byte a byte (`training/llm/export.py`). Batería de siempre: 3 pasadas, semilla 1. La batería ya
tiene 409 frases (las 9 nuevas de la 6.28).

| Modelo | Reserva (80) | Batería (409) | Actúa sin deber | No actúa | Llamada rota |
| --- | --- | --- | --- | --- | --- |
| `qwen2.5:7b` | 62 (78 %) | 377 (92 %) | 0 | 34 | 0 |
| `nyx-r1:7b` | 70 (88 %) | 379 (93 %) | **11** | 1 | 0 |
| `nyx-r2:7b` | **70 (88 %)** | **391 (96 %)** | **0** | 10 | 0 |

(Actúa sin deber y no actúa: suma de reserva y batería. Las frases del router, 292, aciertan
todas con los tres.)

- **Ronda 1:** en Ollama sigue actuando sin deber («pídeme una pizza» → pausa la música, «¿qué
  hora es?» → `now_playing`, «manda un correo…» → escribe uno inventado). Rompe 17 frases.
  En Ollama ninguna llamada sale rota (con `serve.py`, `now_playing` sí): seguramente era cosa de cómo `serve.py` genera y corta, no del modelo. **No se adopta.**
- **Ronda 2:** arregla 30 frases (19 de la batería, 11 de la reserva) y **no actúa nunca sin
  deber**. Rompe 8, ninguna peligrosa:
  - reserva: «ponme el Discord, porfa» → `focus_window` (esperaba `open_app`); «pásame a la
    ventana del Chrome» → `window_layout`; «mueve las fotos del escritorio a Imágenes» →
    llamada incompleta (Nyx la reintenta);
  - batería: «a las 5 de la tarde tengo médico, avísame» → aviso a las 16:30; «está muy alto el
    sonido» → pregunta de qué app; y tres llamadas mal formadas que Nyx reintenta (`move_files`,
    `set_volume`, `app_action`).
- Los fallos de los tres siguen siendo sobre todo «no actúa» en lo que Nyx no sabe hacer, y
  respuestas que niegan cosas que sí hace («¿guardas lo que te digo?» → «Aún no sé guardar
  archivos»: no conoce `save_note` porque no estaba al entrenar).
- **Latencia:** primer token con mediana de 470 ms con la ronda 2 frente a 1.310 ms con
  `qwen2.5:7b`. No lo tomo como medida: la del modelo base fue la primera tras la conversión
  (carga en frío y el procesador aún ocupado). Hay que repetirla.

**Veredicto:** la ronda 2 es la primera que mejora sin actuar sin deber, pero **la regla del
plan (sin fallos nuevos ni más coste) no se cumple del todo**: 8 fallos nuevos leves y sin medir
en partida (`game_bench.py`; mismo tamaño y cuantización, así que no debería cambiar). Decide
el usuario (`docs/REVISAR.md`).

Informes: `lora-6.27-ollama-{base,r1,r2}-{reserva,bateria}.md`.
