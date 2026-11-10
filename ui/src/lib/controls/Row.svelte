<!--
  Fila de una tarjeta: nombre (y explicación) a la izquierda y el control a la derecha.
  Con `stacked`, el control va debajo a todo lo ancho (deslizadores, selectores largos).
-->
<script lang="ts">
  import type { Snippet } from "svelte";

  interface Props {
    label: string;
    hint?: string | null;
    value?: string | null;
    stacked?: boolean;
    children: Snippet;
  }
  let { label, hint = null, value = null, stacked = false, children }: Props = $props();
</script>

<div class="row" class:stacked>
  <div class="text">
    <span class="label">
      {label}
      {#if value}<span class="value">{value}</span>{/if}
    </span>
    {#if hint}<span class="hint">{hint}</span>{/if}
  </div>
  <div class="control">
    {@render children()}
  </div>
</div>

<style>
  .row {
    display: flex;
    align-items: center;
    gap: 16px;
    min-height: 52px;
    padding: 10px 0;
  }

  .stacked {
    flex-direction: column;
    align-items: stretch;
    gap: 6px;
  }

  .text {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  .label {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    font-size: 14px;
  }

  .value {
    color: var(--text-secondary);
    font-variant-numeric: tabular-nums;
  }

  .hint {
    font-size: 12px;
    line-height: 1.4;
    color: var(--text-secondary);
  }

  .control {
    display: flex;
    flex: none;
    justify-content: flex-end;
  }

  .stacked .control {
    flex: auto;
    justify-content: stretch;
  }

  .stacked .control > :global(*) {
    flex: 1;
  }
</style>
