# Licencia del modelo de activación «Nyx» (`nyx-v1.onnx` y `nyx-v1.pt`)

© 2026 Tomás Palencia (Tepnyx).

Estos dos archivos (el modelo que reconoce la palabra «Nyx», en ONNX y en PyTorch) se publican
bajo la licencia **Creative Commons Atribución-CompartirIgual 4.0 Internacional (CC BY-SA
4.0)**: <https://creativecommons.org/licenses/by-sa/4.0/deed.es>. El resto del código de Nyx
sigue bajo GPL-3.0 (`LICENSE`, en la raíz).

Se entrenaron con datos de otros, algunos con licencias que piden atribución o compartir
igual. Por eso el modelo se publica con la misma licencia que los más exigentes y cita a todos:

| Datos | Uso en el entrenamiento | Licencia |
| --- | --- | --- |
| openWakeWord (David Scripka): modelos `melspectrogram` y `embedding_model` | Rasgos de audio | Apache-2.0 |
| Voces de Piper (proyecto Rhasspy/Open Home Foundation) `es_ES-davefx` | Ejemplos sintéticos de «Nyx» | CC0 |
| Voz de Piper `es_ES-carlfm` | Ejemplos sintéticos | Dominio público |
| Voz de Piper `es_MX-ald` | Ejemplos sintéticos | Unlicense |
| Voz de Piper `es_ES-sharvard` | Ejemplos sintéticos | CC BY 3.0 (según su ficha de modelo) |
| Voz de Piper `en_US-libritts` (corpus LibriTTS) | Ejemplos sintéticos | CC BY 4.0 |
| OpenSLR 28 (ruidos y respuestas al impulso de sala) | Ruido de fondo | Apache-2.0 |
| OpenSLR 61, 71 y 72 (Google: habla en español de Argentina, Chile y Colombia) | Habla que no es «Nyx» | CC BY-SA 4.0 |

Las grabaciones de voz del autor no forman parte del entrenamiento (solo se usaron para
medir). Detalle y fuentes: `docs/LICENCIAS.md`. Los modelos de palabras de openWakeWord (CC
BY-NC-SA) no se usan.

Si redistribuyes o modificas estos archivos: cita esta lista y comparte el resultado bajo CC
BY-SA 4.0.
