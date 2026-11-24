# Plan «Cerebro 2»: oído, turnos, router y LLM (borrador)

Estado: **borrador del 2026-11-22; respuestas del usuario del 2026-11-23 incorporadas (§7).
Pendiente de su visto bueno.** Va **antes de la beta 0.9.0**.
Objetivo, en palabras del usuario: un asistente que parezca humano, que sepa con seguridad qué
hacer y que, cuando no lo sepa, **convierta la duda en una conversación corta en vez de
equivocarse**, lo más rápido posible y sin molestar en partida.

## 0. De dónde partimos (2026-11-22)

| Pieza | Cómo es ahora | Por qué falla |
| --- | --- | --- |
| Audio | Silero VAD, sin supresión de ruido | Con música o juego, Whisper oye islandés o alemán (ERRORES). |
| Whisper | large-v3-turbo q5, Vulkan, `temperature 0`, pista fija `"Nyx."` | La pista no lleva los nombres de apps y juegos del equipo (la SPEC §5 lo pide). No se usa la confianza de Whisper: una transcripción mala se trata igual que una buena. Un solo intento. |
| Fin de frase | 700 ms de silencio; a los 0,4 s se transcribe y se mira si el router la entiende o acaba en «?»; lista de palabras que dejan la frase a medias | Reglas de texto: corta a quien piensa en voz alta y espera de más a quien ya ha terminado. No oye la entonación. |
| Router | ~130 reglas de expresiones regulares en orden fijo (22 temas) | Muy preciso en lo que conoce (255/255), pero frágil ante cualquier forma de decirlo que no esté escrita y ante errores de Whisper. Cada frase nueva es una regla más. |
| LLM | `qwen2.5:7b` (+ LoRA r2), Ollama, 44 herramientas en un prefijo de ~4.350 tokens | Lento para lo que hace (0,4–2 s), a veces contesta en texto en vez de actuar, y en partida compite por la gráfica: −3,1 % de FPS de media, pero el usuario nota los tirones cuando piensa. |
| Dudas | Casi no hay: o actúa, o «Aún no sé hacer eso» | No hay una política de «no estoy seguro → pregunto». |

Batería actual: 390/409 frases de texto. **No hay batería de audio real**: no sabemos cuánto
falla el oído ni el fin de frase, que es donde el usuario nota más los errores.

### 0.1 Lo que dicen los registros de este PC (18–23 de noviembre)

`%LOCALAPPDATA%\Nyx\logs\core.log`, `activaciones\` y `actions\`:

1. **La activación es el problema número uno.** 448 activaciones del detector de «Nyx»: **433
   falsas** (97 %) y 15 de verdad. El 19-11, 180 falsas frente a 6 buenas. Whisper descarta las
   falsas, pero **cada una es una transcripción en la gráfica** (200–450 ms): con juego o música,
   una por minuto o más. Lo que «oye» Whisper en ellas: «Gracias.» 261 veces (la alucinación
   típica de Whisper con ruido o silencio), «-», «Y», «¿Qué?»… El umbral sube solo hasta 0,65
   y aun así siguen (mediana de las falsas: 0,77).
2. **El tirón en partida** (19-11, 03:24, «Hostia, me acaba de laguear Nyx») coincide con
   activaciones falsas y una pregunta al LLM. Muy probablemente el tirón lo dan sobre todo las
   verificaciones de Whisper repetidas, no solo el LLM. C0 lo medirá por separado.
3. **Palabras mal oídas sin pedir aclaración**: «Keraes», «Queudáis», «Dikto» (→ el LLM contestó
   «¿Cómo te puedo ayudar, Dikto?»), «Applelepic Games» (→ explicó qué es Epic Games en vez de
   abrirlo; el usuario tuvo que repetirlo), «Al través, deshazlo».
4. **Actuar con un dato mal entendido**: «Apunta el blog de notas, pizza caprese» → guardó una
   nota titulada «pizza caprese» con el texto «blog de notas»; «Apunta.» → nota con «pizza capr»;
   «Pizza campesina» (en dictado) → escribió `pizza campesina»` con la comilla. Y se aprendieron
   esos atajos malos («apunta» → aquella nota). Tres veces seguidas hubo que deshacer.
5. **Peticiones compuestas**: «Cierra todas las aplicaciones y apaga el ordenador» y «Cierra todo
   y apaga el ordenador» → buscó una app llamada «todas las aplicaciones» / «todo» y no hizo nada;
   hasta la tercera forma («cierra el Opera y cierra el Spotify y…») no funcionó.
6. **Conversación que no iba para Nyx** («Para que no tenga nix bien hecho no me voy a decir
   nada…») recibió respuesta.
7. **Latencia**: «¿Qué hora es?» fue al LLM y tardó 3,5 s (y la línea pequeña salió en inglés,
   «what time is it»); las del router, 10–30 ms.

## 1. La idea en una frase

Pasar de «reglas + LLM» a una cadena de **piezas pequeñas, entrenadas y medidas**, cada una con
su **confianza**, y un **gestor de conversación** que decide con esa confianza y con el riesgo de
la acción: actuar, confirmar, preguntar o pasar al LLM.

```text
micro → limpieza de ruido → VAD → Whisper (con pista de vocabulario y confianza por palabra)
      → detector de fin de turno (audio + texto) ─┐
                                                   ↓
   corrector de nombres (fonético, contra apps/juegos/archivos/contactos del equipo)
                                                   ↓
   1) reglas actuales (precisión 100 %, se quedan como primera red)
   2) NLU entrenado en la CPU: intención + datos + confianza (5–20 ms, 0 % de gráfica)
   3) LLM solo para planes, conversación, preguntas y lo que el NLU no tiene claro
                                                   ↓
   gestor de diálogo: confianza × riesgo → actuar / confirmar / preguntar / LLM
```

Lo que más gana, en orden: **medir con audio real** → **NLU en la CPU** (rápido, sin gráfica,
tolera errores de Whisper) → **fin de turno** → **preguntar en vez de fallar** → **LLM más
pequeño y especializado** (menos FPS perdidos).

## 2. Objetivos medibles (en este PC, con la batería de audio)

| Métrica | Hoy | Objetivo |
| --- | --- | --- |
| Acción equivocada ejecutada (lo peor) | sin medir con audio | **< 0,5 %**; con acciones rojas, 0 |
| Petición resuelta bien a la primera o tras una pregunta | sin medir | ≥ 95 % |
| Preguntas de aclaración innecesarias | — | < 5 % |
| Cortes a media frase / esperas de más (> 1 s) | sin medir | < 2 % / < 5 % |
| Fin de frase → empieza la acción (router o NLU) | ~0,7–1 s | **< 0,45 s** (p50) |
| Fin de frase → primera palabra (LLM) | 0,9–2,5 s | < 1,0 s (p50), < 1,8 s (p95) |
| WER de Whisper con juego o música de fondo | sin medir | −30 % sobre hoy |
| FPS en partida pensando cada 8 s | −3,1 % media, tirones | < 2 % media y **1 % lows ≤ −3 %** |

## 3. Fases

Cada fase: plan corto con archivos → visto bueno → hacer → medir en este PC (calidad, latencia,
CPU, RAM, VRAM y FPS) → prueba del usuario → visto bueno. Ninguna fase cambia el
comportamiento por defecto si no mejora la batería; todo detrás de un ajuste hasta adoptarlo.

### C0. Banco de pruebas de verdad (antes de tocar nada)

Sin esto no sabremos si una mejora mejora.

- **Batería de audio**: ~400 frases grabadas por el usuario (y, si quieren, testers) en 4
  condiciones: silencio, música, juego de fondo y lejos del micro. Etiquetadas con lo que
  debía hacer Nyx. Incluye frases cortadas a propósito, pausas para pensar, correcciones
  («no, el otro») y frases que no van para Nyx. Se graban con `record_samples.py` ampliado; los
  fondos se pueden mezclar después (una grabación limpia × varios fondos = muchas pruebas).
- **Métricas de cada etapa por separado**: WER y acierto de nombres (oído), cortes y esperas
  (turnos), intención y datos (router/NLU), acción final y latencias p50/p95.
- **Medidor de recursos**: CPU, RAM, VRAM y uso de gráfica durante la batería; y en partida,
  tiempos de fotograma con PresentMon (MIT) para ver los tirones (1 % y 0,1 % lows), no solo
  la media. Amplía `game_bench.py`.
- **Errores reales** (solo en local): cuando el usuario corrige a Nyx («no, eso no»), se guarda
  el audio y lo que pasó en `%LOCALAPPDATA%\Nyx\aprender\` para alimentar las rondas
  siguientes. Con permiso explícito y borrable.

### C0b. Activación: «Nyx» sin falsos y sin gastar gráfica (primero, tras C0)

Lo que más molesta según los registros (§0.1). Objetivo: < 1 activación falsa por hora jugando,
≥ 97 % de «Nyx» de verdad detectados y **ninguna verificación en la gráfica** en partida.

1. **Guardar el audio de cada activación** (las 433 falsas de estos días se han perdido; solo
   queda el texto). Son los mejores negativos posibles: el ruido real de este PC.
2. **Reentrenar el detector propio** con esos negativos, con audio de juegos y música mezclado,
   «gracias», «y», «¿qué?»… y con más positivos grabados por el usuario.
3. **Verificar sin Whisper grande**: un segundo detector en la CPU (modelo de palabras clave o
   un reconocedor pequeño) en lugar de large-v3-turbo en la gráfica. Whisper solo cuando el
   segundo también lo da por bueno.
4. **«Gracias.» y los demás alucinados no cuentan nunca** como verificación, y la probabilidad
   de «no hay voz» de Whisper se usa para descartar.
5. **Quitar lo que suena del PC** del micro (cancelación de eco con la salida de audio como
   referencia), si el usuario juega con altavoces.

### C1. Oído: que entienda aunque el audio sea malo

1. **Limpieza de ruido** antes del VAD: DeepFilterNet 3 (MIT/Apache, tiempo real en CPU) frente
   a RNNoise (BSD). Se mide WER con y sin; solo se adopta si mejora.
2. **Pista de vocabulario dinámica**: apps, juegos, carpetas y contactos del equipo, más las
   palabras del contexto (lo que Nyx acaba de preguntar). Con cuidado: una pista larga hace
   que Whisper se invente esos nombres; se mide.
3. **Confianza por palabra** (whisper-server devuelve probabilidades por token): si una palabra
   clave sale con poca confianza, segundo intento con búsqueda en haz (beam 5) o la pista
   ajustada, y si sigue dudosa, el gestor pregunta solo por esa palabra («¿has dicho Steam o
   Teams?»).
4. **Corrector de nombres fonético**: comparar por sonido en español (no letra a letra como
   `_fix_typo`) contra el catálogo del equipo. «la cotón» → «melocotón», «dis cord» → Discord.
5. **Otro idioma**: si sale otro idioma con poca confianza, se repite forzando español antes de
   descartar (pendiente de ERRORES).
6. **Comparar otro reconocedor**: Parakeet TDT 0.6B v3 (multilingüe con español; corre en la
   CPU con ONNX) frente a Whisper. Si en CPU es bueno, en partida el oído dejaría la gráfica
   libre. Su licencia hay que confirmarla (unos sitios dicen CC BY 4.0 y NVIDIA habla de su
   licencia de modelos abiertos): te aviso antes de usarlo.
7. **Más tarde (C7)**: ajustar Whisper con un LoRA a voz de órdenes en español con ruido.

### C2. Turnos: saber si has terminado, sigues o lo has dejado a medias

1. **Smart Turn v3** (Pipecat, BSD-2, 8 MB, en la CPU, 23 idiomas, ~90 % en español): mira la
   entonación de los últimos segundos y dice si el turno ha terminado. Se combina con:
2. **Clasificador de texto** entrenado (terminada / a medias / duda) sobre lo transcrito a cada
   pausa, en lugar de las listas de palabras.
3. **Espera adaptativa**: terminada y clara → cortar a 250–300 ms; a medias → esperar hasta
   2–3 s; si pasa el tiempo y sigue a medias, Nyx no actúa: «¿Sí? ¿Qué carpeta?».
4. **Continuación**: si vuelves a hablar justo después de que Nyx cierre la frase, se une a lo
   anterior en vez de tomarlo como petición nueva.
5. Se afina con la batería (cortes < 2 %, esperas de más < 5 %).

### C3. Router nuevo: NLU entrenado en la CPU

El cambio más grande. Las reglas no se tiran: se quedan delante (aciertan el 100 % de lo suyo)
y sirven para generar datos.

1. **Esquema de intenciones**: cada herramienta (y cada forma útil de usarla) es una
   intención con sus datos (app, número, hora, archivo…). Sale del registro de herramientas.
2. **Modelo**: un codificador multilingüe pequeño (clase XLM-R/mDeBERTa/E5 «small», 100–250 M)
   con dos cabezas: intención y etiquetado de datos. Cuantizado a int8 en ONNX, en la CPU:
   **5–20 ms y nada de gráfica**, así que en partida no cuesta FPS.
3. **Datos** (la clave): decenas de miles de frases.
   - Plantillas × nombres reales × formas de hablar (cercana, borde, con muletillas, a medias).
   - Paráfrasis de un modelo «profesor» grande (ver §5).
   - **Pasadas por el oído**: frase → voz sintética de varias voces → ruido de juego/música →
     Whisper → texto con los errores reales de Whisper. Así el NLU aprende a entender lo que
     Whisper transcribe de verdad, no el texto perfecto.
   - Negativas: frases que no son para Nyx o que piden algo que no existe.
4. **Confianza calibrada** y detección de «esto no lo conozco» (fuera de dominio), para saber
   cuándo pasar al LLM.
5. **Resolución de datos** contra el índice del sistema (fonética + difusa), con empates
   detectados (dos «Spotify») para que el gestor pregunte.
6. Se mide contra las reglas y el LLM en la batería; se adopta por intención: donde el NLU
   gane, entra.

### C4. Gestor de diálogo: dudas que se convierten en conversación

1. **Política confianza × riesgo** (sin tocar los niveles de la SPEC §8): confianza alta →
   actúa (las rojas, con su confirmación de siempre); **ante cualquier duda, pregunta, también
   en las verdes** (decisión del usuario, 2026-11-23: mejor una pregunta que un error). Un
   atajo solo se aprende de una acción que no se deshizo ni corrigió después.
2. **Preguntas mínimas**: preguntar solo lo que falta o lo dudoso, con opciones si las hay
   («¿La carpeta Fotos de Descargas o la del escritorio?»), y entender la respuesta corta
   («la segunda», «la del escritorio», «ninguna»).
3. **Correcciones**: «no, el otro», «más alto», «eso no»: deshacer y rehacer con lo corregido,
   y guardarlo como preferencia.
4. **Estado de la conversación** explícito (qué se está haciendo, qué falta), no solo los 6
   últimos turnos en texto.
5. **Sonar humano mientras piensa**: si la respuesta va a tardar más de ~0,6 s, un acuse corto
   («a ver…», «vale, lo busco») con variantes por tono; poder interrumpir a Nyx hablando.

### C5. LLM: más pequeño, más listo para Nyx y más rápido

1. **Motor**: probar `llama-server` de llama.cpp (MIT, Vulkan) frente a Ollama: gramáticas
   (la salida de herramientas no puede salir mal formada), probabilidades por token (confianza
   del LLM), caché de prefijo controlada, decodificación especulativa con un modelo pequeño de
   borrador, y prioridad baja de la cola de la gráfica (a investigar). Si gana, cambio de la
   SPEC §6 (te lo propondría aparte).
2. **Menos prompt**: el NLU ya trae la intención y los candidatos; el LLM recibe solo las
   herramientas relevantes y un sistema más corto. Menos tokens = menos tiempo de gráfica.
3. **Elegir modelo otra vez** con la batería nueva: los 7–9B y 3–4B de la generación actual
   (Qwen3.5 4B y 9B, Gemma 4 E4B, Granite 4.1 3B…; los de la 6.21 eran la generación anterior).
   La pregunta no es cuál acierta más sin entrenar, sino **cuál acierta más tras entrenarlo
   para Nyx** por tiempo de gráfica.
4. **Entrenamiento en varias rondas** (en este PC con ROCm, como la 6.27):
   - SFT con un conjunto mucho mayor: multi-turno, aclaraciones, correcciones, planes de
     varios pasos, negativas, respuestas con el tono de Nyx.
   - DPO (preferencias): pares «actuar bien» frente a «contestar en texto», «preguntar»
     frente a «inventarse un dato», para que aprenda a preguntar cuando duda.
   - Uno o varios LoRA: por ejemplo uno de herramientas y otro de conversación, cargados según
     el caso (llama.cpp permite cambiar LoRA sin recargar el modelo).
5. **Dos tamaños**: el modelo grande fuera de partida y uno de 3–4B (ajustado igual) en
   partida, que ocupa la mitad de gráfica. A medir si cambiar de modelo al entrar en partida
   da tirones (con el 14B los daba).

### C6. Partida: que pensar no se note

1. Medir tirones de verdad (tiempos de fotograma) mientras Nyx piensa, no solo la media.
2. En partida, el NLU (CPU) resuelve casi todo; el LLM solo para preguntas.
3. Modelo pequeño en partida (C5.5), respuestas más cortas y tope de tokens.
4. Prioridad de la gráfica: probar colas de baja prioridad de Vulkan y, si llama.cpp no lo
   permite, trocear la generación con pausas para no robar fotogramas seguidos.
5. Opción de poner el oído en la CPU durante la partida si C1.6 sale bien.

### C7. Whisper ajustado a Nyx (más caro, cuando lo anterior esté)

LoRA de Whisper turbo con: grabaciones del usuario (C0), Common Voice en español (CC0), frases
de Nyx con voces sintéticas y ruido de juegos/música. Se convierte a ggml y se usa igual en
whisper.cpp. Solo se adopta si baja el WER de la batería de audio sin subir la latencia.

### C8. Pulido humano

Tono que se adapta a la conversación, latencias por debajo del objetivo en todos los caminos,
y la batería de audio pasando con la voz propia de Nyx cuando esté grabada.

### C9. Cada parte en su lenguaje (estudio del 2026-11-24, `docs/LENGUAJES.md`)

1. **Voz sin PyTorch**: la voz propia de Nyx se entrena en formato Piper/VITS y se exporta a
   ONNX; al adoptarla salen torch y pocket-tts del núcleo (−~300 MB de RAM y varios segundos
   de arranque; −518 MB de paquete).
2. **Bucle del micro**: medirlo con py-spy en C0b; solo si sale caro, pasarlo a Rust (PyO3).
3. Las piezas nuevas (C2, C3, C1.4, C5.1) se hacen ya con motores nativos (ONNX Runtime,
   `tokenizers`, rapidfuzz, llama-server).

### Hecho fuera de orden (2026-11-24)

- **C5.1, motor `llama-server`** (con el visto bueno del usuario, para quitar Ollama): ver §10.

## 4. Orden y dependencias

```text
C0 ── C0b ─┬─ C1 ── C2 ──┐
           └─ C3 ────────┼── C4 ── C6 ── C8
               C5 ───────┘        C7 (en paralelo cuando haya datos)
```

C0 primero, sin excepción, y C0b justo después (es lo que más molesta). C1/C2 y C3 pueden ir a la vez (unos días con el PC entrenando y
otros midiendo audio). C3 es el que más gana y el que más tarda.

## 5. Sobre usar a Claude (y servidores) para esto

- **Como profesor durante el desarrollo** (decisión del usuario, 2026-11-23: Nyx no compite
  con Claude ni con ningún servicio de Anthropic): Claude genera y revisa en las sesiones
  frases, paráfrasis, diálogos de aclaración y correcciones, etiqueta errores y juzga
  respuestas. Además, un profesor abierto en local (Apache-2.0) para generar en volumen por la
  noche cuando haga falta más cantidad.
- **Como cerebro dentro de Nyx**: no. **Nada de nube** (decisión 2026-11-23); el nivel 3 de la
  SPEC §6 queda fuera.
- **Cómputo**: todo en este PC (decisión 2026-11-23), aunque tarde días. Lo que no quepa en
  12 GB se adapta (modelos más pequeños, QLoRA, lotes por la noche).

## 6. Licencias a confirmar antes de usar

| Pieza | Licencia | Estado |
| --- | --- | --- |
| Smart Turn v3 | BSD-2 | comprobar al empezar C2 |
| DeepFilterNet 3 | MIT / Apache-2.0 | comprobar |
| Parakeet TDT 0.6B v3 | CC BY 4.0 o licencia NVIDIA (fuentes contradictorias) | **avisar antes** |
| Codificador del NLU | según el elegido (MIT/Apache) | comprobar |
| Common Voice es | CC0 | ok |
| Modelos candidatos del LLM | según cada uno | comprobar (algunos tienen licencias propias) |
| PresentMon | MIT | comprobar |

## 7. Respuestas del usuario (2026-11-23)

| # | Pregunta | Respuesta |
| --- | --- | --- |
| 1 | Dónde va | **Antes de la beta 0.9.0.** |
| 2 | Batería de audio | Graba el usuario lo que haga falta; los testers no. |
| 3 | Claude como profesor | Sí: Nyx no compite con Claude ni con Anthropic. |
| 4 | Cómputo | Todo en este PC. |
| 5 | Nube | Nada de nube (el nivel 3 de la SPEC queda fuera). |
| 6 | llama-server en vez de Ollama | Sí, si gana en las mediciones. |
| 7 | Ante la duda | **Preguntar**, también en acciones verdes. |
| 8 | Qué molesta | Revisar los registros de este PC: hecho (§0.1). |
| 9 | Guardar audio de correcciones | Sí (en local). |
| 10 | Equipo mínimo | El portátil nunca fue el mínimo: cuanto más abajo funcione, mejor. Las pruebas, solo en este PC y en el portátil. |

**Fondos para la batería de audio (pregunta 2).** Se graban las frases en silencio y, aparte,
unos minutos de lo que suele sonar mientras se usa Nyx; luego se mezclan a varios volúmenes.
Así cada frase se prueba en 4–6 situaciones sin grabarla otra vez. Hace falta saber:

- **Juegos** a los que más juegas (Rocket League y Valorant salen en los registros: ¿alguno
  más?). Se graba el sonido del juego tal como lo coge tu micro.
- **Música**: la que sueles poner (Spotify), con y sin voz.
- **Voces**: Discord con amigos o vídeos de YouTube de fondo (son lo más difícil: voces que no
  son para Nyx).
- **¿Altavoces o cascos?** Si juegas con altavoces, el micro coge el juego y la música y hace
  falta quitarlos (C0b.5); con cascos, casi no.

**Respondido el 2026-11-23:** Rocket League, Valorant y Fortnite; **cascos**; micrófono Ozone
(RecX50); orden C0 → C0b → resto aprobado. Con cascos, el micro apenas coge el juego: lo que
más ensucia son la propia voz hablando con otros (Discord), el teclado y el ratón, y lo que se
escape de los cascos. Aun así, se graba también el sonido de los juegos por la salida de audio
(sin micro) para probar con altavoces, que es lo que tendrán otros usuarios.

## 9. C0 en detalle (aprobado el 2026-11-23; hecho el 2026-11-23, falta grabar)

**Qué se consigue:** una batería de audio real y un informe de base (hoy) de cada etapa: activación,
fin de frase, transcripción, entender y actuar, latencias y recursos; y Nyx empieza a guardar
(en local) el audio de lo que falla para entrenar.

| # | Archivo | Qué hace |
| --- | --- | --- |
| 1 | `%APPDATA%\Nyx\settings.json` | Activar `wake.save_false_clips` (ya existe, 6.22) desde hoy: cada activación falsa deja su audio. |
| 2 | `core/tests/battery/audio/guion.jsonl` | ~400 frases con lo que debe pasar (herramienta y datos, o «preguntar», o «no es para Nyx»). Tipos: órdenes normales, nombres difíciles (Valorant, Fortnite, Opera GX…), compuestas, con pausas para pensar, a medias, correcciones («no, el otro»), frases que no van para Nyx, y «Nyx» suelto. Las saca de `frases.jsonl` y de §0.1 y añade las nuevas. Va en git (solo texto). |
| 3 | `core/scripts/record_battery.py` | Grabación guiada por tandas de 50 (≈ 8 min cada una): enseña la frase y cómo decirla («con una pausa a la mitad», «déjala a medias»), graba con el micro de Nyx, permite repetir, y sigue donde se quedó. El audio se queda en `%LOCALAPPDATA%\Nyx\training\bateria-audio\` (nunca en git: es tu voz). |
| 4 | `core/scripts/record_background.py` | Graba fondos: (a) el micro mientras juegas con cascos y hablas por Discord; (b) la salida de audio (loopback, sin micro) de Rocket League, Valorant, Fortnite y música, para simular altavoces. 3–5 min de cada. |
| 5 | `core/scripts/audio_battery.py` | Pasa la batería por la cadena real de Nyx sin interfaz, mezclando cada frase con cada fondo a 2–3 volúmenes. Mide por separado: activación (aciertos y falsas por hora con los fondos), fin de frase (cortes y esperas de más), WER y nombres bien oídos, intención y datos, acción final (bien / mal / preguntó / nada) y latencias p50/p95. Con `--informe` escribe `docs/benchmarks/audio-<equipo>-<fecha>.md`. |
| 6 | `core/scripts/resmon.py` | Medidor de recursos para usarlo con el anterior y con `game_bench.py`: CPU y RAM de cada proceso de Nyx (núcleo, whisper-server, Ollama) y uso de gráfica y VRAM por proceso (contadores de Windows, valen para AMD y NVIDIA). |
| 7 | `core/scripts/game_bench.py` | Ampliado: además del LLM, configuraciones que aíslan **las verificaciones de «Nyx»** (una por minuto, como en los registros) y la transcripción sola; informe con 1 % y 0,1 % lows y número de tirones (fotogramas > 2× la mediana). |
| 8 | `core/nyx/learn/store.py` (+ ajuste `learn.save_corrections`, apagado por defecto) | Cuando se deshace o corrige algo («deshazlo», «no, eso no», «no, el otro»), guarda el audio, lo transcrito y lo que hizo Nyx en `%LOCALAPPDATA%\Nyx\aprender\`. En tu equipo, activado. Se borra con el resto de datos de Nyx (papelera, nunca borrado permanente). |
| 9 | Pruebas: `core/tests/test_audio_battery.py`, `test_learn_store.py`, `test_resmon.py` | Mezcla a un volumen dado, cálculo de métricas, guardado de correcciones y lectura de contadores (con datos falsos). |

**Lo que harás tú:** grabar la batería (≈ 1 h en tandas, cuando quieras) y los fondos (una
partida de cada juego con `record_background.py` en marcha), y jugar una vez con
`game_bench.py`. **Lo que haré yo:** todo lo demás, el informe de base y, con él, el plan
corto de C0b.

No cambia nada de lo que hace Nyx salvo los puntos 1 y 8 (guardar audio en local).

### 9.1 Hecho (2026-11-23)

- Código en `core/nyx/bench/` (audio, guion, métricas, arnés, recursos) y `core/nyx/learn/`;
  scripts `record_battery.py`, `record_background.py`, `audio_battery.py` y `game_bench.py`
  ampliado; pruebas en `core/tests/test_bench.py` y `test_learn_store.py`.
- Guion: `core/tests/battery/audio/guion.jsonl`, 394 frases (activación 8, órdenes 153,
  nombres 30, compuestas 20, pausas 27, a medias 18, correcciones 24 en 12 grupos, preguntas
  32, ambiguas 24, no para Nyx 26, dictado 12, de fallos reales 20).
- Arnés probado con 14 frases sintéticas (voz de Piper): funciona de punta a punta y ya caza
  fallos reales: «Battle.net» se abre como web; «cierra el Opera y el Spotify y apaga…»
  busca una app llamada «opera y spotify…»; una pausa de 1,5 s en «abre la carpeta de…
  Descargas» corta la frase («No encuentro de.»); «apunta en el bloc de notas…» llega a abrir
  los Ajustes de Nyx; y con charla de fondo actúa sobre lo que oye en la ventana de
  seguimiento. El informe base se hace con tus grabaciones.
- En el PC del usuario: activados `wake.save_false_clips` y `privacy.save_corrections` (el
  segundo, solo con la versión de desarrollo o la próxima compilación).
- Visto de paso: el Nyx instalado usa `qwen2.5:7b`, no `nyx-r2:7b`; y el servicio de AMD
  Software (`AMDRSServ.exe`) tiene ~5,4 GB de VRAM reservados (a mirar en C6).

### 9.2 Qué tiene que hacer el usuario

1. **Cerrar Nyx** (bandeja → Salir) y grabar la batería por tandas de 50:
   `uv run python scripts/record_battery.py` (desde `core/`; ~8 tandas de ~8 min).
2. **Fondos**, una partida de cada (con Nyx abierto o cerrado, sin decir «Nyx»):
   `uv run python scripts/record_background.py rocket`, `valorant`, `fortnite`; y
   `musica --solo-salida` (Spotify con canciones con voz) y `discord --solo-micro` (hablando
   con amigos).
3. Cuando esté, Claude pasa `audio_battery.py` (≈ 1,5 h por condición, mejor de noche) y
   escribe el informe base; luego, una vez, `game_bench.py` como administrador con el juego
   abierto.

## 10. C5.1 adelantado: el cerebro sin Ollama (hecho el 2026-11-24, falta medirlo)

**Qué se consigue:** Nyx lanza y vigila ella misma el cerebro con `llama-server` (llama.cpp,
MIT), como ya hace con whisper-server: el usuario no instala nada más, no queda nada abierto
al salir y se puede controlar lo que Ollama no deja (gramáticas, confianza por palabra, caché
del prefijo, LoRA sin recargar). **Apagado por defecto** (`llm.engine: "ollama"`) hasta medirlo.

| Archivo | Qué hace |
| --- | --- |
| `core/nyx/brain/llamacpp.py` | `LlamaCppEngine`: la misma interfaz que el de Ollama, por la API compatible con OpenAI (SSE). Junta las llamadas a herramientas que llegan a trozos; esquema JSON por gramática; caché del prefijo; semilla; un reintento si el servidor no responde. |
| `core/nyx/brain/llamacpp_process.py` | `LlamaServer`: lanza `llama-server` oculto en un puerto libre con `-np 1`, `--jinja`, todo en la GPU elegida por Vulkan (`-v --list-devices`, la dedicada si no se elige); se cierra con Nyx; si con la GPU no arranca, sigue con la CPU (N-411). «Liberar la VRAM» = pararlo. Con el cerebro de Nyx o Qwen 2.5 pasa la plantilla oficial de Qwen 2.5 (`nyx/brain/data/qwen2.5.jinja`), porque el GGUF de Nyx se hizo para Ollama. |
| `core/nyx/settings/model.py` | `llm.engine` (`ollama` / `llamacpp`), `llm.server`, `llm.model_path`, `llm.gpu`. |
| `core/nyx/services.py` | Elige el motor; avisos N-410 (no arranca o falta el cerebro) y N-411 (con la CPU), sin hablar de Ollama. |
| `core/nyx/setup/brain.py` y `service.py` | Con `llamacpp`, el primer arranque baja los trozos del cerebro y los une en un `.gguf` comprobando la huella del total (D-221), sin Ollama. |
| `core/scripts/fetch_llama.py` | Baja la compilación oficial de llama.cpp con Vulkan, **versión fija `b12240` (2026-11-10) y su SHA-256**, con las variantes de CPU ya incluidas; solo `llama-server`, sus DLL y las licencias (86 MB). |
| `core/scripts/package_core.py`, `scripts/build-release.ps1` | `--llama` / `-Llama` (o NYX_LLAMA_DIR; si no, lo baja): `core\bin\llama`. |
| `core/scripts/battery.py`, `game_bench.py` | `--motor llamacpp` y las configuraciones `llamacpp@gpu` / `llamacpp@cpu`. |
| Pruebas | `tests/test_llamacpp.py` (motor y proceso, 18), `test_brain_download.py` (+3), `test_startup_notice.py` (+2). |

Comprobado en el portátil: el zip coincide con su huella, `llama-server` arranca con solo los
archivos elegidos y ve las dos gráficas (la integrada con `uma: 1`). No se ha cargado ningún
modelo aquí (pruebas pesadas, solo en el PC).

### 10.1 Qué tiene que hacer el usuario (en el PC)

Desde `core/`, con Nyx cerrada (bandeja → Salir):

1. `uv sync` y `uv run python scripts/fetch_llama.py` (→ `%LOCALAPPDATA%\Nyx\llama`).
2. El cerebro ya está en el PC, dentro de Ollama: es el archivo
   `C:\Users\<usuario>\.ollama\models\blobs\sha256-d323312a31bcf9418fb7cf2a814c48e214bd6466d99239cf97bd945b2a1c7441`
   (la huella de `cerebro.json`). En `%APPDATA%\Nyx\settings.json`, dentro de `"llm"`:
   `"model": "nyx-r2:7b"` y `"model_path": "<esa ruta, con \ dobles>"`. Sin cambiar `engine`.
3. Batería con los dos motores, misma semilla:
   `uv run python scripts/battery.py --motor ollama --modelo nyx-r2:7b` y
   `uv run python scripts/battery.py --motor llamacpp`.
4. Partida, como administrador y con el juego abierto:
   `uv run python scripts/game_bench.py --presentmon <ruta> --process RocketLeague.exe --configs sin nyx-r2:7b@gpu llamacpp@gpu`.
5. Si va bien, `"engine": "llamacpp"` en los ajustes, abrir Nyx y usarla un día: que no se
   abra ninguna consola, que conteste igual y que al salir no quede `llama-server` abierto.

**Se adopta si** la batería no baja (±2 frases), el primer token y la respuesta no son más
lentos, en partida no pierde más FPS ni da más tirones, y el uso normal va bien. Entonces:
quitar Ollama del instalador y del primer arranque, y el cambio en la SPEC §6.
