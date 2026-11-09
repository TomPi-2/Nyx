<!--
  La isla (SPEC sección 12): pastilla de cristal gris arriba en el centro del monitor.
  Fase 1: versión provisional con tinte (sin desenfoque real) y un orbe en CSS;
  el orbe con shader WebGL llega en la fase 5.
-->
<script lang="ts">
  import { onMount } from "svelte";
  import { Spring } from "svelte/motion";
  import { invoke } from "@tauri-apps/api/core";
  import { connectCore } from "$lib/core";
  import type { NyxState, ServerMessage } from "$lib/protocol";

  const TOP = 12; // margen superior en px
  const MAX_WIDTH = 520;
  const HIDE_AFTER_MS = 400; // deja terminar la animación de salida antes de ocultar la ventana

  let status = $state<NyxState>("idle");
  let connected = $state(false);
  let bubble = $state<{ display: string; secondary: string | null } | null>(null);
  let measuredW = $state(0);
  let measuredH = $state(0);

  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)");
  const springOpts = { stiffness: 0.12, damping: 0.62 };
  const width = new Spring(44, springOpts);
  const height = new Spring(44, springOpts);
  const level = new Spring(0, { stiffness: 0.3, damping: 0.8 });

  const shown = $derived(connected && (status !== "idle" || bubble !== null));

  /** Tamaño objetivo según el estado (sección 12: 44×44 escuchando, 120×44 pensando). */
  const target = $derived.by(() => {
    if (bubble) return { w: Math.min(MAX_WIDTH, measuredW), h: measuredH };
    if (status === "thinking" || status === "muted") return { w: 120, h: 44 };
    return { w: 44, h: 44 };
  });

  $effect(() => {
    const instant = reduceMotion.matches;
    void width.set(target.w, { instant });
    void height.set(target.h, { instant });
  });

  // Mostrar la ventana al salir de reposo y ocultarla del todo al volver.
  let hideTimer: ReturnType<typeof setTimeout> | undefined;
  $effect(() => {
    clearTimeout(hideTimer);
    if (shown) {
      void invoke("island_set_visible", { visible: true });
    } else {
      hideTimer = setTimeout(
        () => void invoke("island_set_visible", { visible: false }),
        HIDE_AFTER_MS,
      );
    }
  });

  function handle(msg: ServerMessage) {
    switch (msg.type) {
      case "state":
        status = msg.state;
        break;
      case "level":
        level.target = msg.rms;
        break;
      case "bubble":
        bubble = { display: msg.display, secondary: msg.secondary };
        break;
      case "bubble_hide":
        bubble = null;
        break;
    }
  }

  onMount(() =>
    connectCore(handle, (ok) => {
      connected = ok;
      if (!ok) {
        status = "idle";
        bubble = null;
      }
    }),
  );
</script>

<!-- Medidor invisible: tamaño natural del contenido de la burbuja. -->
{#if bubble}
  <div class="bubble-content measure" bind:clientWidth={measuredW} bind:clientHeight={measuredH}>
    <span class="display">{bubble.display}</span>
    {#if bubble.secondary}<span class="secondary">{bubble.secondary}</span>{/if}
  </div>
{/if}

<div
  class="island"
  class:shown
  class:error={status === "error"}
  class:muted={status === "muted"}
  class:thinking={status === "thinking" && !bubble}
  style:top="{TOP}px"
  style:width="{width.current}px"
  style:height="{height.current}px"
>
  {#if bubble}
    <div class="bubble-content">
      <span class="display">{bubble.display}</span>
      {#if bubble.secondary}<span class="secondary">{bubble.secondary}</span>{/if}
    </div>
  {:else}
    <div
      class="orb"
      class:speaking={status === "speaking"}
      style:transform="scale({0.75 + level.current * 0.55})"
    ></div>
  {/if}
</div>

<style>
  .island {
    position: absolute;
    left: 50%;
    translate: -50% 0;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    border-radius: 22px;
    background: var(--glass-sheen), var(--glass-fallback);
    box-shadow: var(--shadow);
    opacity: 0;
    scale: 0.96;
    filter: blur(6px);
    transition:
      opacity 220ms ease,
      scale 320ms cubic-bezier(0.34, 1.4, 0.64, 1),
      filter 260ms ease;
  }

  .island.shown {
    opacity: 1;
    scale: 1;
    filter: blur(0);
  }

  .island.muted {
    opacity: 0.5;
  }

  /* Pensando: un brillo blanco recorre la isla de izquierda a derecha. */
  .island.thinking::after {
    content: "";
    position: absolute;
    inset: 0;
    background: linear-gradient(
      90deg,
      transparent 0%,
      rgba(255, 255, 255, 0.18) 50%,
      transparent 100%
    );
    translate: -100% 0;
    animation: sweep 1.1s ease-in-out infinite;
  }

  .island.error {
    animation: shake 380ms ease;
  }

  .orb {
    width: 22px;
    height: 22px;
    border-radius: 50%;
    background: radial-gradient(
      circle at 50% 45%,
      var(--glow) 0%,
      rgba(210, 210, 215, 0.85) 38%,
      rgba(150, 150, 158, 0.35) 70%,
      transparent 100%
    );
    box-shadow: 0 0 18px rgba(255, 255, 255, 0.35);
  }

  .orb.speaking {
    animation: shimmer 140ms linear infinite alternate;
  }

  .bubble-content {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    padding: 14px 26px;
    max-width: 520px;
    white-space: nowrap;
  }

  .measure {
    position: absolute;
    visibility: hidden;
    pointer-events: none;
  }

  .display {
    font-family: "Segoe UI Variable Display", "Segoe UI", system-ui, sans-serif;
    font-size: 28px;
    font-weight: 600;
    color: var(--text);
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
  }

  .secondary {
    font-size: 13px;
    color: var(--text-secondary);
  }

  @keyframes sweep {
    to {
      translate: 100% 0;
    }
  }

  @keyframes shake {
    20%,
    60% {
      translate: calc(-50% - 6px) 0;
    }
    40%,
    80% {
      translate: calc(-50% + 6px) 0;
    }
  }

  @keyframes shimmer {
    to {
      filter: brightness(1.15);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .island,
    .island.thinking::after,
    .island.error,
    .orb.speaking {
      transition: none;
      animation: none;
    }
  }
</style>
