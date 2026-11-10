<!--
  Panel de respuesta (SPEC sección 11): el dato clave grande y una línea secundaria.
  Si hay texto para leer (una frase larga en el dato, o la respuesta entera en la línea
  secundaria de las peticiones escritas), se muestra como párrafo alineado a la izquierda.
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
  const LONG_DISPLAY = 44;
  const LONG_SECONDARY = 90;
  const longDisplay = $derived(display.length > LONG_DISPLAY || display.includes("\n"));
  const longSecondary = $derived(
    !longDisplay &&
      secondary !== null &&
      (secondary.length > LONG_SECONDARY || secondary.includes("\n")),
  );
</script>

<div
  class="panel"
  class:long={longDisplay || longSecondary}
  style:max-width="{PANEL_MAX_WIDTH}px"
  use:glassShape={{ radius: PANEL_RADIUS }}
  use:glassPoke
>
  {#if longDisplay}
    <p class="body">{display}</p>
    {#if secondary}<span class="note">{secondary}</span>{/if}
  {:else if longSecondary}
    <span class="title">{display}</span>
    <p class="body">{secondary}</p>
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

  .title {
    font-family: "Segoe UI Variable Display", "Segoe UI", system-ui, sans-serif;
    font-size: 20px;
    font-weight: 600;
    line-height: 1.2;
  }

  .body {
    margin: 0;
    font-size: 15px;
    line-height: 1.45;
    white-space: pre-line;
    /* Respuestas muy largas: se desplazan por dentro en vez de llenar la pantalla. */
    max-height: 260px;
    overflow-y: auto;
    scrollbar-width: thin;
    scrollbar-color: var(--control) transparent;
  }

  .note {
    font-size: 12px;
    color: var(--text-tertiary);
  }
</style>
