# LoRA de qwen2.5:7b (6.27) · PC de referencia (RX 7700 XT)

## Cómo se mide

Ollama 0.40 no importa un Qwen2 ajustado (ver `core/training/llm/README.md`) y la conversión a
GGUF con llama.cpp queda pendiente de permiso. Para decidir si el LoRA merece la pena,
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

## Ronda 2 (en curso) · 970 ejemplos, mismos ajustes

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

Aparte, «gracias» suelto ya no llega al modelo: lo contesta Nyx con variantes por tono
(`brain/answers.py`). En la batería sigue llegando al modelo (mide al modelo, no a Nyx).
