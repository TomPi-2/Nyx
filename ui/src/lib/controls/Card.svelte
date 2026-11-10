<!--
  Grupo de opciones (SPEC sección 13): tarjeta redondeada de 20 px en `glass-raised`. Las
  filas se separan con espacio, nunca con líneas.
-->
<script lang="ts">
  import type { Snippet } from "svelte";

  interface Props {
    title?: string;
    note?: string;
    children: Snippet;
  }
  let { title, note, children }: Props = $props();
</script>

<section class="group">
  {#if title}<h3>{title}</h3>{/if}
  <div class="card">
    {@render children()}
  </div>
  {#if note}<p class="note">{note}</p>{/if}
</section>

<style>
  .group {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  h3 {
    margin: 0 0 0 16px;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.02em;
    color: var(--text-secondary);
  }

  .card {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 6px 16px;
    border-radius: 20px;
    background: var(--glass-raised);
  }

  .note {
    margin: 0 16px;
    font-size: 12px;
    line-height: 1.45;
    color: var(--text-tertiary);
  }
</style>
