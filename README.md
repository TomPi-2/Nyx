# Nyx

Asistente de voz y texto para Windows 11 que ejecuta acciones en el PC y responde preguntas. Funciona en local, gratis y sin ventana propia.

> «Nyx, abre Valorant» → se abre sin decir nada.
> «Nyx, ¿cómo se dice hola en alemán?» → responde por voz y muestra «Hallo» en una burbuja.

**Estado:** en desarrollo, fase 1 de 6 (base y pruebas técnicas).

## Arquitectura

Dos procesos que hablan por WebSocket local:

- **`core/`**: núcleo en Python 3.12. Escucha (openWakeWord, Silero VAD), transcribe (whisper.cpp con Vulkan), decide (router rápido + Ollama), actúa (herramientas de Windows) y habla (Kokoro).
- **`ui/`**: interfaz en Tauri 2 + TypeScript. Solo dibuja: una isla de cristal gris en la parte superior del monitor y burbujas flotantes.

La especificación completa está en [docs/SPEC.md](docs/SPEC.md).

## Requisitos

- Windows 11
- Node.js 22 y Rust (para Tauri 2)
- uv (gestiona Python 3.12)
- GPU con Vulkan (referencia: AMD Radeon RX 7700 XT, 12 GB VRAM)

## Desarrollo

```powershell
cd ui
npm install
npm run tauri dev
```

Arranca la app completa: el icono de Nyx aparece en la bandeja y la isla recorre sus estados en modo demo. Desde la bandeja se abre la prueba de cristal. Necesita [uv](https://docs.astral.sh/uv/), que instala Python 3.12 solo.

## Fases

1. Base y pruebas técnicas
2. Bucle de voz
3. Acciones
4. «Nyx» de verdad (modelo de activación propio)
5. Modo partida e interfaz final
6. Pulido y distribución

Después: fase 7, personalización de la interfaz.
