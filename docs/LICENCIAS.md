# Auditoría de licencias y de lo que se publica

Revisión del 2026-11-13, antes de hacer público el repositorio (CLAUDE.md, «Antes de hacer
público el repositorio»). No es asesoramiento legal: es lo que dicen las licencias que declara
cada pieza, comprobado una a una. Lo que necesita una decisión está en **Pendiente**, al final.

## Resumen

- **Código de Nyx:** GPL-3.0 (`LICENSE`). `ui/package.json` y `ui/src-tauri/Cargo.toml` dicen
  `GPL-3.0-only`, y `core/pyproject.toml` también desde el 2026-11-13 (decisión del usuario).
  **Excepción (2026-11-14, decisión del usuario):** `core/nyx/ext/manifest.py`, `content.py` y
  `signing.py` son `GPL-3.0-only OR MIT` (cabecera SPDX), para que el kit de extensiones (MIT)
  valide igual que Nyx. Al montar el kit (7.13) hay que llevarse también, con MIT, lo pequeño
  que importan del núcleo (`Risk`/`GamePolicy`, la tabla de teclas, `normalize` y la lista de
  ajustes editables) o copiarlo dentro del kit.
- **Python del núcleo (9.07) y de las extensiones (7.05–7.07):** el «embeddable» oficial de python.org, 3.14.10
  (licencia PSF-2.0, compatible con GPL; firmado por la Python Software Foundation). Se
  descarga con su huella SHA-256 (`nyx/ext/runtime.py`). `nyx/ext/runner.py`, lo que corre
  dentro, también tiene licencia MIT, como el kit. Cuando se distribuya
  con Nyx, su `LICENSE.txt` va al lado y a los créditos.
- **Todas las dependencias que se distribuyen son compatibles con GPL-3.0.** Ninguna es de
  pago ni prohíbe distribuir.
- **Hay que citar autores** (CC BY, ODbL, OFL): falta una pantalla de créditos en Ajustes →
  Ayuda y un `NOTICE`/créditos junto al instalador (tarea para la 0.9).
- **La voz contratada no va con el código**: se distribuye aparte, con su propia licencia
  (ver «Voz propia de Nyx»).
- **Historial de git:** sin claves, tokens ni contraseñas. Datos personales: tu correo como
  autor en 170 commits, el usuario de Windows en 5 líneas antiguas y el nombre del equipo en
  los informes (ver «Historial»).

## Dependencias de Python (núcleo, 87 paquetes en Windows)

Sacado de `uv export --no-dev` y de los metadatos de cada paquete instalado.

| Licencia | Paquetes |
| --- | --- |
| MIT / MIT-0 | anyio, cffi, comtypes, fastapi, filelock, h11, onnxruntime, pydantic, pycaw, rapidfuzz, screen-brightness-control, sounddevice, setuptools, typer, urllib3, rich, pyyaml, mss, wmi, winrt-*, einops, pocket-tts (código) y otros |
| Apache-2.0 o BSD-3 | cryptography (firma de extensiones, 0.7) |
| BSD-2/3 | httpx, httpcore, click, idna, numpy (+ 0BSD, Zlib, CC0), psutil, send2trash, starlette, uvicorn, websockets, scipy, sympy, networkx, protobuf, pygments, markupsafe, jinja2 |
| Apache-2.0 | requests, huggingface-hub, hf-xet, watchdog, sentencepiece, tokenizers, safetensors, flatbuffers, vosk, python-multipart, opentelemetry-api, packaging (o BSD) |
| MPL-2.0 | certifi, tqdm (+ MIT) |
| PSF / ISC | pywin32 (pypiwin32 es solo un alias suyo), typing-extensions; shellingham |
| GPL-3.0-or-later | piper-tts |
| Varias (Apache-2.0, BSD, MIT, Zlib, BSL-1.0…) | torch 2.15.0 **+cpu** (sin CUDA ni ROCm) |

Los paquetes de NVIDIA/CUDA y `triton` aparecen en el bloqueo pero con `sys_platform == 'linux'`:
**en Windows no se instalan** (y `torch` es la versión para CPU). Regla del proyecto cumplida.

Apache-2.0 y MPL-2.0 son compatibles con GPL-3.0 (en el sentido de distribuirlas juntas).

## Interfaz

- **npm (lo que va en la app):** `@tauri-apps/api` y `@tauri-apps/plugin-notification`
  (MIT o Apache-2.0); fuentes `@fontsource-variable/manrope` y `nunito` (**OFL-1.1**: hay que
  incluir su licencia con la app). Segoe UI es de Windows (no se distribuye).
- **Rust (262 crates para Windows, `cargo metadata`):** MIT o Apache-2.0 casi todas; además
  Unicode-3.0, Zlib, BSD-3-Clause, Unlicense/MIT, BSL-1.0, CC0 y **MPL-2.0** (`cssparser`,
  `selectors`, `dtoa-short`, `option-ext`, de WebView/Tauri; compatible). Ninguna GPL salvo Nyx.

## Modelos

| Modelo | Uso | Licencia | Obligaciones |
| --- | --- | --- | --- |
| qwen2.5:7b (Ollama, lo descarga el usuario) | Cerebro | Apache-2.0 | El LoRA ajustado se puede distribuir; incluir la licencia y el aviso de Qwen si se distribuye |
| Whisper large-v3-turbo (ggml de whisper.cpp) | Voz a texto | MIT | — |
| whisper-server (whisper.cpp) | Voz a texto | MIT | — |
| Silero VAD 5.1.2 | Detección de voz | MIT | — |
| openWakeWord: melspectrogram y embedding_model | Rasgos para «Nyx» | Apache-2.0 (Google speech_embedding) | Los modelos de palabras de openWakeWord (CC BY-NC-SA) **no** se usan |
| `nyx-v1.onnx` (propio, en el repositorio) | Activación «Nyx» | **CC BY-SA 4.0** (`core/nyx/wake/data/LICENSE-nyx-v1.md`) | Atribuir los datos de entrenamiento (en ese archivo) |
| Vosk small es 0.42 | Palabra personalizada | Apache-2.0 | — |
| Pocket TTS (Kyutai) | Voz | Código MIT; **pesos CC BY 4.0** | **Citar a Kyutai** en la app y la documentación |
| Voz «lola» (Pocket TTS) | Voz predeterminada | Clip de Common Voice (CC0) | — |
| Piper es_ES-davefx | Voz alternativa | CC0 | — |
| Piper es_AR-daniela | Voz alternativa | **CC BY-SA 4.0** (OpenSLR 61) | Citar a Google/OpenSLR 61 |

**`nyx-v1.onnx`** se entrenó con: rasgos de openWakeWord (Apache-2.0), voces de Piper davefx
(CC0), carlfm (dominio público), ald (Unlicense), **sharvard (CC BY 3.0)** y **libritts (CC BY
4.0)**, ruidos de OpenSLR 28 (Apache-2.0) y habla de **OpenSLR 61, 71 y 72 (CC BY-SA 4.0)**. Tus
grabaciones no (`training/build.py`: solo para evaluar). Si un modelo entrenado cuenta como
obra derivada de sus datos no está claro; lo prudente: **publicar `nyx-v1.onnx` bajo CC BY-SA
4.0** citando todas esas fuentes (CC declara CC BY-SA 4.0 compatible con GPL-3.0 en un solo
sentido, así que puede ir con el código).

**Herramientas de desarrollo** (no van en Nyx): Unsloth, TRL, transformers (Apache-2.0), PyTorch
ROCm (BSD-3), bitsandbytes (MIT), llama.cpp (MIT).

## Servicios en internet

| Servicio | Para qué | Condiciones | Obligación |
| --- | --- | --- | --- |
| Open-Meteo | Tiempo | Datos CC BY 4.0, gratis sin clave para uso no comercial | Citar «Open-Meteo» |
| Nominatim (OpenStreetMap) | Nombre de la ciudad | ODbL; 1 petición/s, User-Agent propio | «© OpenStreetMap contributors» |
| Wikipedia | Búsqueda | CC BY-SA 4.0 | Decir la fuente (ya se hace) |
| DuckDuckGo (HTML) | Búsqueda | No es un servicio oficial para programas | **Revisar antes de la beta** |
| Google (navegador) | «Búscalo en el navegador» | Lo abre el usuario | — |
| winget | Instalar programas | De Microsoft, en Windows | — |
| Everything (voidtools) | Buscar archivos (opcional) | Gratuito; lo instala el usuario con winget | — |

Si algún día Nyx tiene ingresos (donativos, patrocinios), **Open-Meteo pide su plan de pago
para uso comercial**: revisarlo entonces.

## Voz propia de Nyx (persona contratada)

Condiciones acordadas (contrato privado de cesión, borrador del usuario): cesión mundial,
indefinida y no exclusiva; regalías del 10 % desde 1.000 € de ingresos brutos con tope de 2.000 €;
**los audios fuera de la licencia libre**, «Todos los derechos reservados», y prohibido extraerlos,
modificarlos, venderlos aparte o usarlos para entrenar IA o clonar la voz.

Cómo encaja con el código abierto:

1. **Ni los audios ni el modelo de voz entrenado van en el repositorio.** Se descargan aparte
   en el primer arranque (como los demás modelos, con huella SHA-256), con su archivo de
   licencia propio. Así un fork del código no se lleva la voz y se puede retirar de un sitio.
2. El **modelo de voz** (p. ej. un `.onnx` de Piper) también queda «Todos los derechos
   reservados»: con él se puede decir cualquier frase con esa voz.
3. GPL-3.0 permite distribuir junto al programa obras separadas con otra licencia («agregado»,
   sección 5), así que el instalador puede incluir la voz sin que pase a ser GPL.
4. Nyx debe poder cambiar de voz en cualquier momento (ya puede: Pocket y Piper).

Puntos para quien revise el contrato (no son asesoramiento legal):

- Que autorice expresamente a **entrenar un modelo de síntesis con su voz para el proyecto**
  (el borrador lo prohíbe fuera del proyecto, pero no lo permite dentro) y que el modelo
  tenga las mismas restricciones que los audios.
- La LO 1/1982 (art. 2.3) hace **revocable** el consentimiento en cualquier momento, con
  indemnización de daños y expectativas justificadas: conviene regular cómo se calcula.
- Definir «ingresos brutos del proyecto» para un programa gratuito (donativos, patrocinios,
  versiones de pago…).

## Historial de git (171 commits, todas las ramas)

- **Claves, tokens, contraseñas, claves privadas:** ninguna (búsqueda de patrones de OpenAI,
  GitHub, AWS, Google, Hugging Face, Slack, claves PEM y asignaciones `password=`/`token=`).
- **Archivos sensibles:** ninguno (sin `.env`, certificados, bases de datos ni ajustes).
- **Datos personales:**
  - Tu nombre y **correo** como autor de 170 commits (`Tomás Palencia` y `TomPi`). Se verán.
  - El usuario de Windows en 5 líneas de informes antiguos (`C:\Users\…\Downloads`, registros
    de whisper). Los archivos actuales ya no lo tienen.
  - El nombre del equipo («TomPi») en los nombres de varios informes de `docs/benchmarks`.
- Para ocultar el correo hay que **reescribir el historial** (`git filter-repo` con un mailmap
  al correo `noreply` de GitHub) antes de publicar: cambia todos los commits. Decisión tuya.

## Pendiente

1. ~~GPL-3.0-only o -or-later~~ **«only»** en todo (2026-11-13; con el CLA, Tepnyx puede
   relicenciar si hiciera falta).
2. **Correo en el historial:** dejarlo o reescribir el historial antes de publicar.
3. **Créditos en la app** (Ayuda → Licencias) y archivo de avisos con el instalador (0.9):
   Kyutai, OpenSLR/Google, Piper (sharvard, libritts, daniela), Open-Meteo, OpenStreetMap,
   Qwen y las fuentes OFL.
4. ~~Licencia de `nyx-v1.onnx`~~ **Hecho:** CC BY-SA 4.0 con las atribuciones
   (`core/nyx/wake/data/LICENSE-nyx-v1.md`, también para `nyx-v1.pt`).
5. **DuckDuckGo** antes de la beta.
6. ~~Contrato de la voz~~ **Hecho** (en Word, fuera del repositorio; lo revisa un abogado).
7. CLA, `SECURITY.md` y `CONTRIBUTING.md`: **aceptados por el usuario** (2026-11-13). El CLA
   conviene que lo mire también el abogado antes de aceptar contribuciones de fuera.
