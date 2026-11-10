<!--
  Panel de respuesta (SPEC sección 11): el dato clave grande y una línea secundaria.
  Las respuestas largas (frases, no datos) se leen mejor como párrafo alineado a la izquierda.
-->
<script lang="ts">
  import { glassPoke, glassShape } from "$lib/glass";
  import { PANEL_MAX_WIDTH, PANEL_RADIUS } from "./layout";

  interface Props {
    display: string;
    secondary?: string | null;
  }
  let { display, secondary = null }: Props = $props();

  /** A partir de aquí es un texto para leer, no un dato. */
  const LONG_AFTER = 44;
  const long = $derived(display.length > LONG_AFTER || display.includes("\n"));
</script>

<div
  class="panel"
  class:long
  style:max-width="{PANEL_MAX_WIDTH}px"
  use:glassShape={{ radius: PANEL_RADIUS }}
  use:glassPoke
>
  {#if long}
    <p class="body">{display}</p>
    {#if secondary}<span class="note">{secondary}</span>{/if}
  {:else}
    <span class="display">{display}</span>
    {#if secondary}<span class="secondary">{secondary}</span>{/if}
  {/if}
</div>

<style>
  .panel {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    min-width: 220px;
    padding: 18px 28px 20px;
    border-radius: 26px;
    text-align: center;
  }

  .display {
    font-family: "Segoe UI Variable Display", "Segoe UI", system-ui, sans-serif;
    font-size: 28px;
    font-weight: 600;
    line-height: 1.15;
    letter-spacing: -0.01em;
  }

  .secondary {
    font-size: 13px;
    color: var(--text-secondary);
  }

  .long {
    align-items: flex-start;
    gap: 8px;
    padding: 18px 22px 18px;
    text-align: left;
  }

  .body {
    margin: 0;
    font-size: 15px;
    line-height: 1.45;
    white-space: pre-line;
  }

  .note {
    font-size: 12px;
    color: var(--text-tertiary);
  }
</style>
