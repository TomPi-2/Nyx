<!--
  Botón en pastilla (SPEC sección 12): gris sobre `control`; el principal en `control-active`.
  Con `confirm`, la primera pulsación pide confirmación («¿Seguro? Vuelve a pulsar») y la
  segunda hace la acción (para lo que manda cosas a la papelera).
-->
<script lang="ts">
  import type { Snippet } from "svelte";

  interface Props {
    primary?: boolean;
    disabled?: boolean;
    confirm?: string | null;
    onclick?: () => void;
    children: Snippet;
  }
  let { primary = false, disabled = false, confirm = null, onclick, children }: Props = $props();

  let asking = $state(false);
  let timer: ReturnType<typeof setTimeout> | undefined;

  function press() {
    if (confirm && !asking) {
      asking = true;
      clearTimeout(timer);
      timer = setTimeout(() => (asking = false), 4000);
      return;
    }
    asking = false;
    onclick?.();
  }
</script>

<button class:primary={primary || asking} {disabled} onclick={press}>
  {#if asking}{confirm}{:else}{@render children()}{/if}
</button>

<style>
  button {
    flex: none;
    padding: 8px 16px;
    border: none;
    border-radius: 999px;
    background: var(--control);
    color: var(--text);
    font: inherit;
    font-size: 13px;
    white-space: nowrap;
    cursor: pointer;
    transition:
      background 160ms ease,
      color 160ms ease,
      transform 120ms ease;
  }

  button:active:not(:disabled) {
    transform: scale(0.97);
  }

  .primary {
    background: var(--control-active);
    color: var(--text-on-active);
    font-weight: 600;
  }

  button:disabled {
    color: var(--text-tertiary);
    cursor: default;
  }

  /* El principal desactivado («Descargando…») conserva su texto oscuro, más apagado: con el
     gris terciario sobre el fondo claro no se leía. */
  .primary:disabled {
    color: var(--text-on-active);
    opacity: 0.55;
  }
</style>
