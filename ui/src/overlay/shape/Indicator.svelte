<!--
  La forma de Nyx (SPEC sección 12). Aísla el indicador para la fase 7 (otros estilos):
  recibe el estado de Nyx, el nivel de audio y el tamaño, y nada más.
-->
<script lang="ts">
  import { onMount } from "svelte";
  import type { NyxState } from "$lib/protocol";
  import { NyxShape, SHAPE_PAD, type ShapeState } from "./nyxShape";

  interface Props {
    status: NyxState;
    level: number; // RMS del micro (escuchando) o de la voz de Nyx (hablando)
    size: number; // lado del cuadrado en px
    backdrop: number | null; // luminancia alrededor (0-1)
    onvisible?: (visible: boolean) => void;
  }
  let { status, level, size, backdrop, onvisible }: Props = $props();

  const VOICE_ON = 0.02; // RMS a partir del cual el usuario está hablando
  const VOICE_HOLD_MS = 450; // sin voz durante esto → vuelve a «espera»

  let canvas: HTMLCanvasElement | undefined = $state();
  let shape: NyxShape | undefined;
  let lastVoice = 0;

  function shapeState(s: NyxState, rms: number): ShapeState {
    switch (s) {
      case "listening": {
        const now = performance.now();
        if (rms > VOICE_ON) lastVoice = now;
        return now - lastVoice < VOICE_HOLD_MS ? "listening" : "waiting";
      }
      case "thinking":
        return "thinking";
      case "speaking":
        return "speaking";
      case "confirm":
      case "error":
        return "waiting";
      default:
        return "hidden";
    }
  }

  onMount(() => {
    if (!canvas) return;
    try {
      shape = new NyxShape(canvas, size);
    } catch (e) {
      console.error("La forma de Nyx necesita WebGL", e);
      return;
    }
    // Avisa cuando la forma termina de desaparecer (para ocultar la ventana entonces).
    let wasVisible = false;
    const poll = setInterval(() => {
      const v = shape?.visible ?? false;
      if (v !== wasVisible) {
        wasVisible = v;
        onvisible?.(v);
      }
    }, 100);
    return () => {
      clearInterval(poll);
      shape?.destroy();
    };
  });

  $effect(() => {
    if (!shape) return;
    shape.size = size;
    shape.setLevel(level);
    shape.setState(shapeState(status, level));
  });

  $effect(() => {
    if (shape && backdrop !== null) shape.setBackdrop(backdrop);
  });
</script>

<canvas
  bind:this={canvas}
  class="shape"
  style:width="{size * SHAPE_PAD}px"
  style:height="{size * SHAPE_PAD}px"
  aria-hidden="true"
></canvas>

<style>
  .shape {
    display: block;
    pointer-events: none;
  }
</style>
