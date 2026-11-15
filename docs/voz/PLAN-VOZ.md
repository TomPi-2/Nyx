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
