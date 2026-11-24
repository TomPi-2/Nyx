# Qué lenguaje para cada parte de Nyx (estudio del 2026-11-24)

Pregunta del usuario: ¿se pueden usar en ciertas partes lenguajes más óptimos para que Nyx sea
lo más rápido, fiable y eficiente posible? Respuesta corta: **Nyx ya está casi así**. Todo el
cálculo pesado va en código nativo (C/C++); Python solo coordina. Hay una pieza que no encaja
(la voz en PyTorch) y una que se decide midiendo (el bucle del micro). Reescribir el núcleo no
compensa.

## 1. Cómo está hoy

| Parte | Lenguaje | ¿Encaja? |
| --- | --- | --- |
| Proceso principal, bandeja, ventanas, actualizaciones, instalador (`ui/src-tauri`, `installer/`) | Rust (Tauri 2), ~3.600 líneas | Sí |
| Interfaz y orbe (`ui/src`) | Svelte 5 + TypeScript + WebGL, ~10.600 líneas | Sí |
| Oído (whisper.cpp), cerebro (llama.cpp, hoy dentro de Ollama), detector de «Nyx» y VAD (ONNX Runtime), Vosk | C/C++ compilado | Sí |
| Coordinación, router, herramientas, APIs de Windows, entrenamiento (`core/nyx`) | Python 3.14, ~37.000 líneas | Sí: reparte trabajo; lo pesado lo hacen librerías nativas (numpy, onnxruntime, rapidfuzz, pywin32) |
| Extensiones (`sdk/`, `extensions/`) | Python (encerradas, 7.05) | Sí: es lo que más gente sabe escribir |
| **Voz «lola» (Pocket TTS)** | **Python + PyTorch en la CPU** | **No** |

## 2. Dónde se va el tiempo

Medido en el PC: Whisper ~170 ms por frase, LLM 0,4–2 s, primer trozo de voz ~80 ms, router
10–30 ms. El código Python que lo une son pocos milisegundos. Pasar el núcleo a Rust o C++
ganaría < 5 % de latencia a cambio de meses de trabajo, del ecosistema de entrenamiento y del
kit de extensiones. **Descartado.**

## 3. Lo que sí se cambia

### 3.1 Voz sin PyTorch (lo que más gana)

Medido en el portátil (2026-11-24), solo importando, sin cargar modelos:

| Paso | Tiempo | RAM del proceso |
| --- | --- | --- |
| numpy + onnxruntime + httpx + pydantic | 0,5 s | 68 MB |
| + torch | +2,0 s | 232 MB |
| + pocket_tts | +7,2 s | 383 MB |

Más los pesos del modelo. Explica casi todo lo apuntado en `benchmarks/requisitos.md` (núcleo
~800 MB frente al objetivo de 600 MB; arranque lento), y torch ocupa 518 MB del paquete.

**Decisión propuesta:** la voz propia de Nyx (decisión del 2026-11-15) se entrena en formato
**Piper/VITS y se exporta a ONNX** (Piper ya va con Nyx y corre en C++). Al adoptarla, torch y
pocket-tts salen del núcleo. Se decide antes de grabar porque condiciona cómo se preparan las
grabaciones (22.050 Hz, frases cortas y limpias, una sola hablante).

### 3.2 Bucle continuo del micro (según se mida)

Micro → rasgos mel → detector de «Nyx» → VAD, cada 32 ms. Los modelos ya van en C++ (ONNX
Runtime), pero el bucle es Python y comparte el núcleo con todo lo demás: si el núcleo está
ocupado, puede haber retrasos. Se mide en el PC con py-spy (MIT) durante C0b. **Solo si sale
caro** se pasa a una extensión en Rust (PyO3 + maturin, MIT/Apache) y Python sigue mandando.

### 3.3 Piezas nuevas de Cerebro 2, en el lenguaje adecuado desde el principio

- LLM: `llama-server` (C++, MIT) lanzado por Nyx, sin Ollama (Go) en medio (C5.1).
- Router entrenado (C3) y detector de fin de turno (C2): ONNX Runtime (C++), con el
  tokenizador `tokenizers` (Rust), no uno escrito en Python.
- Corrector por sonido (C1.4): rapidfuzz (C++), con el catálogo fonético calculado de antemano.

## 4. Lo que no se toca

- Rust/Tauri y Svelte/WebGL: ya son lo adecuado.
- APIs de Windows desde Python (pywin32, comtypes, winrt): no están en el camino crítico.
- Router de reglas (`re` de Python es C por dentro): lo sustituye en parte el NLU (C3).
