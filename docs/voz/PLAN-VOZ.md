# Voz propia de Nyx: plan y guía para dirigir la grabación

Decisiones del usuario (2026-11-15): la voz sustituye a «lola» y será la de Nyx; graba ella
en su equipo, el usuario dirige por Discord (repetir, entonación); muchas horas; se pasan los
archivos por WeTransfer o Google Drive. El contrato lo revisa el abogado (semana del
2026-11-16). Los audios y el modelo entrenado son **todos los derechos reservados**: nunca en
git ni en el repositorio público (`docs/LICENCIAS.md`, «Voz propia de Nyx»).

## Piezas

| Pieza | Dónde | Qué hace |
| --- | --- | --- |
| Guion | `core/training/voz/guion.py` → `tools/grabadora/src/guion.json` | 2.755 frases en 18 sesiones de ~150: lo que dice Nyx, frases de asistente (`frases_nyx.txt`), números en letra y 2.200 frases CC0 de Common Voice escogidas para cubrir los sonidos del español. Cada una con su tono. |
| Grabadora | `tools/grabadora/` → `Releases\grabadora\Grabadora de Nyx.exe` | Un solo `.exe`, sin instalar. Graba sin filtros (WASAPI, mono, 24 bits, a la frecuencia del micrófono), se para sola al callarse, avisa de saturación, volumen bajo, ruido y cortes, guarda las tomas viejas y prepara un `.zip` por sesión. |
| Instrucciones | `docs/voz/INSTRUCCIONES-GRABACION.md` | Para ella: una página, sin tecnicismos. |
| Limpieza | `core/training/voz/` (siguiente paso) | Recortar silencios, igualar volumen, quitar ruido si hace falta (DeepFilterNet, MIT/Apache), comprobar con Whisper que cada audio dice lo que pone el guion. |
| Modelo | (tras la primera hora) | Probar afinar Piper (VITS) y otras opciones abiertas; el usuario elige oyéndolas. |

Para regenerar el guion: `uv run python training/voz/guion.py` (la fuente de Common Voice se
baja con `curl` a `training/voz/fuentes/`, fuera de git). Cambiar el guion después de empezar
a grabar cambia los ids: hacerlo solo antes de la primera sesión, o añadir sesiones al final.

## Cómo dirigir (en la llamada)

- **Primera sesión, primeros 10 minutos:** fijad juntos la distancia al micrófono y el volumen.
  Que grabe 3 frases y escuchadlas («Escuchar»): sin eco, sin ruido y sin saturar. Ese sitio y
  esa distancia, para siempre.
- **Repetir si:** se equivoca en una palabra, cambia una palabra, se ríe, tose, suena un ruido,
  la entonación no encaja con el tono pedido, o la grabadora avisa de algo.
- **No repetir por:** pequeñas diferencias de ritmo o de entonación natural. La variedad es
  buena para el modelo.
- **Ritmo:** 150 frases son unos 40 minutos con repeticiones. Descanso cada media hora.
- **Constancia:** mismo micrófono, sitio, hora del día parecida y la misma «Nyx» (cercana,
  tranquila). Si un día tiene la voz cansada o resfriada, mejor no grabar.
- **Al acabar:** «Preparar para enviar» y te pasa el `.zip`. Guárdalos en
  `%LOCALAPPDATA%\Nyx\voz\grabaciones\` (fuera del repositorio).

## Siguiente

Con la primera sesión recibida: comprobar las tomas (`tomas.jsonl` trae el análisis de cada
una), limpiar y montar el primer conjunto de entrenamiento. Con la primera hora: probar los
modelos y escucharlos juntos antes de que grabe el resto.

## Otros idiomas con su acento (decisión del usuario, 2026-11-18)

Que «¿cómo se dice hola en inglés?» suene *hello* con acento inglés (un poco españolizado
vale), y en general que las palabras de otro idioma no se lean como en español.

**El guion:** las sesiones 19 a 21 (305 frases, `core/training/voz/frases_idiomas.txt`)
son solo para esto: «En inglés se dice «thank you».», palabras sueltas y nombres en inglés,
francés, italiano, alemán y portugués, y apps y juegos dichos como en su idioma («Te abro
YouTube»). Cada frase lleva su idioma y una **pista** de cómo suena, que la grabadora enseña
debajo del texto y no se lee. Se graban al final, sin tocar las 18 primeras. Con ellas salen
los sonidos que el español no tiene: la *th* inglesa, la *h* aspirada, las vocales nasales
del francés y el portugués, la *ü* y la *ö*, las dobles del italiano.

**Para dirigir estas sesiones:** que las diga como una española que sabe pronunciarlas, sin
imitar a un nativo. Repetir si una palabra sale leída en español («jello» por *hello*), no por
acento.

**Lo que hace falta además (no basta con grabar):**

1. **Entrenar con fonemas y no con letras.** El texto de cada frase se pasa a fonemas por
   trozos: lo que va fuera de las comillas con el español de `espeak-ng` y lo de dentro con
   el idioma de la frase (`en-us`, `fr`, `it`, `de`, `pt`). Así el modelo aprende qué sonido
   es cada fonema inglés o francés, con su voz. Piper (VITS) entrena así. Con letras, *hello*
   siempre sonará «elo».
2. **Que Nyx marque lo que está en otro idioma** al hablar: las respuestas de «¿cómo se
   dice…?» ya traen el idioma en la cabecera (`[Hallo | hola · alemán]`). Las fijas y el
   modelo marcarán el trozo (por ejemplo `«hello»{en}`) y la voz lo pasará a fonemas con su
   idioma. Los nombres de apps y juegos, con una lista de pronunciaciones.
3. **Probarlo antes de grabar todo:** con la primera hora y la sesión 19, un modelo de prueba
   y escucharlo juntos.

Mientras tanto, la voz de ahora («lola», Pocket TTS) lee todo como en español.
