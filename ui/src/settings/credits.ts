/**
 * Créditos y licencias de lo que va con Nyx (Ajustes → Ayuda; auditoría en docs/LICENCIAS.md).
 * Las licencias CC BY, CC BY-SA y OFL piden citar a sus autores: aquí y en NOTICE.md.
 */

export interface Credit {
  what: string;
  /** Para qué lo usa Nyx. */
  use: string;
  who: string;
  license: string;
  url: string;
  /** La atribución que pide la licencia, si pide alguna. */
  note?: string;
}

export const CREDITS: Credit[] = [
  {
    what: "Nyx",
    use: "La app entera",
    who: "Tepnyx",
    license: "GPL-3.0",
    url: "https://www.gnu.org/licenses/gpl-3.0.html",
  },
  {
    what: "Qwen2.5 7B Instruct",
    use: "El cerebro (ajustado para Nyx)",
    who: "Alibaba Cloud (Qwen)",
    license: "Apache-2.0",
    url: "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct",
    note: "El cerebro de Nyx es Qwen2.5 7B ajustado por Tepnyx.",
  },
  {
    what: "Ollama",
    use: "Ejecuta el cerebro",
    who: "Ollama",
    license: "MIT",
    url: "https://github.com/ollama/ollama",
  },
  {
    what: "Whisper large-v3-turbo y whisper.cpp",
    use: "El oído (voz a texto)",
    who: "OpenAI · Georgi Gerganov y colaboradores",
    license: "MIT",
    url: "https://github.com/ggml-org/whisper.cpp",
  },
  {
    what: "Pocket TTS",
    use: "La voz",
    who: "Kyutai",
    license: "Código MIT · pesos CC BY 4.0",
    url: "https://github.com/kyutai-labs/pocket-tts",
    note: "Voz generada con Pocket TTS, de Kyutai.",
  },
  {
    what: "Piper (voces davefx y daniela)",
    use: "Voces alternativas",
    who: "Rhasspy · davefx · Google (OpenSLR 61)",
    license: "Código MIT · davefx CC0 · daniela CC BY-SA 4.0",
    url: "https://github.com/rhasspy/piper",
    note: "La voz «daniela» sale del conjunto de datos OpenSLR 61, de Google (CC BY-SA 4.0).",
  },
  {
    what: "Silero VAD",
    use: "Saber cuándo hablas",
    who: "Silero Team",
    license: "MIT",
    url: "https://github.com/snakers4/silero-vad",
  },
  {
    what: "openWakeWord",
    use: "Rasgos para reconocer «Nyx»",
    who: "David Scripka",
    license: "Apache-2.0",
    url: "https://github.com/dscripka/openWakeWord",
  },
  {
    what: "Modelo de activación «Nyx» (nyx-v1)",
    use: "Reconocer su nombre",
    who: "Tepnyx",
    license: "CC BY-SA 4.0",
    url: "https://creativecommons.org/licenses/by-sa/4.0/",
    note: "Entrenado con voces de Piper (davefx, carlfm, ald, sharvard CC BY 3.0, libritts CC BY 4.0), ruidos de OpenSLR 28 y habla de OpenSLR 61, 71 y 72 (CC BY-SA 4.0).",
  },
  {
    what: "Vosk (modelo small es 0.42)",
    use: "Palabras de activación personalizadas",
    who: "Alpha Cephei",
    license: "Apache-2.0",
    url: "https://alphacephei.com/vosk/",
  },
  {
    what: "Python",
    use: "El núcleo",
    who: "Python Software Foundation",
    license: "PSF-2.0",
    url: "https://docs.python.org/3/license.html",
  },
  {
    what: "PyTorch y ONNX Runtime",
    use: "Ejecutar la voz y la activación",
    who: "Linux Foundation · Microsoft",
    license: "BSD-3-Clause · MIT",
    url: "https://pytorch.org/",
  },
  {
    what: "Tauri, Svelte y WebView2",
    use: "La interfaz",
    who: "Tauri Programme · Svelte · Microsoft",
    license: "MIT o Apache-2.0",
    url: "https://tauri.app/",
  },
  {
    what: "Velopack",
    use: "Instalar y actualizar",
    who: "Velopack Ltd",
    license: "MIT",
    url: "https://velopack.io/",
  },
  {
    what: "Certificados raíz de Mozilla (webpki-roots)",
    use: "Conexiones seguras al actualizar",
    who: "Mozilla · rustls",
    license: "CDLA-Permissive-2.0",
    url: "https://github.com/rustls/webpki-roots",
  },
  {
    what: "Manrope y Nunito",
    use: "Fuentes opcionales (Apariencia)",
    who: "Mikhail Sharanda · Vernon Adams",
    license: "SIL Open Font License 1.1",
    url: "https://openfontlicense.org/",
  },
  {
    what: "Open-Meteo y OpenStreetMap (Nominatim)",
    use: "El tiempo y el nombre de tu ciudad",
    who: "Open-Meteo · colaboradores de OpenStreetMap",
    license: "CC BY 4.0 · ODbL",
    url: "https://open-meteo.com/",
    note: "Datos del tiempo de Open-Meteo.com (CC BY 4.0). Nombres de lugares © colaboradores de OpenStreetMap (ODbL).",
  },
  {
    what: "Everything (si lo instalas)",
    use: "Buscar archivos en todo el disco",
    who: "voidtools",
    license: "MIT",
    url: "https://www.voidtools.com/",
  },
];
