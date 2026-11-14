<!--
  La onda de «Nyx lista» (9.04): una de estas ventanas por monitor (src-tauri/src/wave.rs).
  Todas reciben el mismo origen y la misma hora de salida en coordenadas del escritorio
  virtual (píxeles físicos), y cada una dibuja su trozo del anillo con el motor de cristal,
  que deforma lo que hay detrás. Así se ve una sola onda que pasa de un monitor a otro. Al
  acabar, la ventana se quita sola.
-->
<script lang="ts">
  import { onMount } from "svelte";
  import { invoke } from "@tauri-apps/api/core";
  import { glass } from "$lib/glass";

  /** Lo que tarda en cruzarlo todo (prototipo: 1,7 s). */
  const DURATION_MS = 1700;
  /** Grosor del anillo al salir y al final (px CSS): se adelgaza hasta disiparse. */
  const RING_START = 70;
  const RING_END = 8;
  /** Si algo falla, la ventana no se queda puesta. */
  const SAFETY_MS = 1500;

  const params = new URLSearchParams(location.search);
  const num = (key: string) => Number(params.get(key) ?? 0);
  const scale = window.devicePixelRatio || 1;
  // Centro y alcance en píxeles CSS de esta ventana (cada monitor con su escala).
  const cx = (num("ox") - num("left")) / scale;
  const cy = (num("oy") - num("top")) / scale;
  const reach = num("reach") / scale;
  const start = num("start");

  let fallback = $state(false);
  let ring: HTMLDivElement | undefined = $state();
  let finished = false;
  /** El motor dice que solo puede teñir (Bajo): entonces no se dibuja nada. */
  let tintOnly = false;

  const easeOut = (k: number) => 1 - Math.pow(1 - k, 3);

  function shape(k: number) {
    const r = reach * easeOut(k);
    const thickness = Math.min(r, RING_END + (RING_START - RING_END) * Math.pow(1 - k, 0.8));
    return { r, thickness };
  }

  function finish() {
    if (finished) return;
    finished = true;
    void invoke("glass_set_shapes", { shapes: [] }).finally(() => {
      glass.detach();
      void invoke("wave_done");
    });
  }

  function frame() {
    if (finished) return;
    const k = (Date.now() - start) / DURATION_MS;
    if (k >= 1) {
      finish();
      return;
    }
    if (k >= 0) {
      const { r, thickness } = shape(k);
      if (fallback) {
        if (ring) {
          ring.style.transform = `translate(${cx - r}px, ${cy - r}px)`;
          ring.style.width = ring.style.height = `${2 * r}px`;
          ring.style.borderWidth = `${thickness}px`;
          ring.style.opacity = String(1 - k * k);
        }
      } else if (!tintOnly) {
        const shapes = [
          { x: cx - r, y: cy - r, w: 2 * r, h: 2 * r, radius: r, wobble: 1, ring: thickness },
        ];
        void invoke("glass_set_shapes", { shapes });
      }
    }
    requestAnimationFrame(frame);
  }

  onMount(() => {
    const dark = matchMedia("(prefers-color-scheme: dark)").matches;
    let unlisten: (() => void) | undefined;
    void (async () => {
      // Cristal casi sin tinte ni desenfoque: la onda es sobre todo refracción y brillo.
      await glass.attach({
        quality: "auto",
        motion: "siempre",
        amplitude: 5,
        speed: 1.6,
        blur: 0.1,
        tint: 0.04,
        refraction: 26,
        saturation: 1.35,
        specular: 0.9,
        shadow: 0,
        dark,
        tintDark: null,
        tintLight: null,
      });
      fallback = document.documentElement.dataset.glass === "css";
      // Si el motor solo puede teñir (Bajo), una onda de tinte no se parece a nada: se quita.
      // Se quita con dos avisos seguidos, por si el primero llega antes de aplicar el nivel.
      let low = 0;
      unlisten = await glass.onStats((stats) => {
        tintOnly = stats.effective === "bajo";
        low = stats.effective === "bajo" ? low + 1 : 0;
        if (low >= 2 || stats.failed) finish();
      });
      requestAnimationFrame(frame);
    })();
    const safety = setTimeout(finish, Math.max(0, start - Date.now()) + DURATION_MS + SAFETY_MS);
    return () => {
      clearTimeout(safety);
      unlisten?.();
    };
  });
</script>

{#if fallback}
  <div class="ring" bind:this={ring}></div>
{/if}

<style>
  :global(html),
  :global(body) {
    background: transparent;
    overflow: hidden;
  }

  /* Sin el motor (sin GPU): un anillo de luz suave en vez de la refracción. */
  .ring {
    position: fixed;
    left: 0;
    top: 0;
    box-sizing: border-box;
    border-radius: 50%;
    border-style: solid;
    border-color: rgba(255, 255, 255, 0.16);
    box-shadow:
      0 0 40px rgba(255, 255, 255, 0.18),
      inset 0 0 40px rgba(255, 255, 255, 0.18);
    pointer-events: none;
  }
</style>
