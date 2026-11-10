<!--
  Deshacer (SPEC sección 8): lo que se ha hecho y un botón «Deshacer» durante 30 s. El fondo
  del botón se vacía según pasa el tiempo, así se ve cuánto queda sin leer números.
-->
<script lang="ts">
  import { onMount } from "svelte";
  import { glassPoke, glassShape } from "$lib/glass";
  import { PANEL_MAX_WIDTH, PANEL_RADIUS } from "./layout";

  interface Props {
    text: string;
    secondary?: string | null;
    undoLabel?: string;
    /** Tiempo para deshacer (ms). */
    durationMs?: number;
    onundo?: () => void;
  }
  let {
    text,
    secondary = null,
    undoLabel = "Deshacer",
    durationMs = 30000,
    onundo,
  }: Props = $props();

  let remaining = $state(1);
  onMount(() => {
    const start = performance.now();
    let frame = 0;
    const tick = () => {
      remaining = Math.max(0, 1 - (performance.now() - start) / durationMs);
      if (remaining > 0) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  });
</script>

<div
  class="panel"
  style:max-width="{PANEL_MAX_WIDTH}px"
  use:glassShape={{ radius: PANEL_RADIUS }}
  use:glassPoke
>
  <span class="icon" aria-hidden="true">
    <svg viewBox="0 0 20 20" width="18" height="18">
      <path
        d="M5 10.5l3.2 3.2L15 7"
        fill="none"
        stroke="currentColor"
        stroke-width="1.8"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
    </svg>
  </span>
  <span class="texts">
    <span class="text">{text}</span>
    {#if secondary}<span class="secondary">{secondary}</span>{/if}
  </span>
  <button
    class="undo"
    style:--left="{remaining * 100}%"
    disabled={remaining <= 0}
    onclick={() => onundo?.()}
  >
    {undoLabel}
  </button>
</div>

<style>
  .panel {
    display: flex;
    align-items: center;
    gap: 12px;
    min-width: 320px;
    padding: 12px 12px 12px 14px;
    border-radius: 26px;
  }

  .icon {
    display: grid;
    flex: none;
    place-items: center;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: var(--glass-raised);
  }

  .texts {
    display: flex;
    flex: 1;
    flex-direction: column;
    min-width: 0;
  }

  .text {
    font-size: 14px;
    font-weight: 600;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .secondary {
    font-size: 12px;
    color: var(--text-secondary);
  }

  .undo {
    flex: none;
    padding: 9px 16px;
    border: none;
    border-radius: 999px;
    /* El relleno claro es el tiempo que queda. */
    background:
      linear-gradient(90deg, rgba(255, 255, 255, 0.16) 0 var(--left), transparent var(--left)),
      var(--control);
    color: inherit;
    font: inherit;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
  }

  .undo:disabled {
    color: var(--text-tertiary);
    cursor: default;
  }
</style>
