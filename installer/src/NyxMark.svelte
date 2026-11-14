<!--
  La forma de Nyx de verdad en el instalador (9.08): la misma de la app (ui/src/overlay/shape),
  con los bordes vivos pero sin girar, y llenándose como un vaso con lo instalado (`fill`,
  0–1; null = entera). En claro, Nyx va en gris oscuro, como en el prototipo.
-->
<script lang="ts">
  import { onMount } from "svelte";
  import { NyxShape, SHAPE_PAD } from "$shape/nyxShape";

  interface Props {
    /** Lado del cuadrado (px CSS). */
    size?: number;
    fill?: number | null;
  }
  let { size = 58, fill = null }: Props = $props();

  let canvas: HTMLCanvasElement | undefined = $state();
  let shape: NyxShape | undefined;
  let failed = $state(false);
  const box = $derived(Math.round(size * SHAPE_PAD));

  function theme(s: NyxShape) {
    const dark = matchMedia("(prefers-color-scheme: dark)").matches;
    s.setColor(dark ? [0.96, 0.96, 0.97] : [0.23, 0.23, 0.24]);
    s.setFill(fill, dark ? [0.47, 0.47, 0.5, 0.3] : [0.47, 0.47, 0.5, 0.2]);
  }

  onMount(() => {
    if (!canvas) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = box * dpr;
    canvas.height = box * dpr;
    try {
      shape = new NyxShape(canvas, size);
    } catch {
      failed = true; // sin WebGL: el cuadrado de CSS
      return;
    }
    shape.spin = false;
    theme(shape);
    shape.setState("listening"); // bordes vivos y tranquilos (la espera se deforma más)
    const scheme = matchMedia("(prefers-color-scheme: dark)");
    const onScheme = () => shape && theme(shape);
    scheme.addEventListener("change", onScheme);
    return () => {
      scheme.removeEventListener("change", onScheme);
      shape?.destroy();
    };
  });

  $effect(() => {
    if (shape) shape.setFill(fill);
  });
</script>

<div class="mark" style:width="{size}px" style:height="{size}px" aria-hidden="true">
  {#if failed}
    <div class="plain" style:--p="{Math.round((fill ?? 1) * 100)}%"></div>
  {:else}
    <canvas bind:this={canvas} style:width="{box}px" style:height="{box}px"></canvas>
  {/if}
</div>

<style>
  .mark {
    position: relative;
    flex: none;
  }

  /* El lienzo es más grande que el cuadrado (sitio para deformarse): centrado encima. */
  canvas {
    position: absolute;
    left: 50%;
    top: 50%;
    transform: translate(-50%, -50%);
    pointer-events: none;
  }

  .plain {
    width: 100%;
    height: 100%;
    border-radius: 42%;
    background: linear-gradient(to top, var(--nyx) var(--p), var(--control) var(--p));
  }
</style>
