<!--
  Confirmación de acciones rojas (SPEC sección 8): resumen claro de lo que va a pasar y dos
  botones en pastilla, el principal en `control-active`. Caduca sola (15 s) y lo dice.
-->
<script lang="ts">
  import { onMount } from "svelte";
  import { glassPoke, glassShape } from "$lib/glass";
  import { PANEL_MAX_WIDTH, PANEL_RADIUS } from "./layout";

  interface Props {
    title: string;
    detail?: string | null;
    confirmLabel?: string;
    cancelLabel?: string;
    /** Cuánto falta para que se cancele sola (ms). */
    expiresMs?: number;
    onconfirm?: () => void;
    oncancel?: () => void;
  }
  let {
    title,
    detail = null,
    confirmLabel = "Confirmar",
    cancelLabel = "Cancelar",
    expiresMs = 15000,
    onconfirm,
    oncancel,
  }: Props = $props();

  let left = $state(0);
  onMount(() => {
    const end = performance.now() + expiresMs;
    const tick = () => (left = Math.max(0, Math.ceil((end - performance.now()) / 1000)));
    tick();
    const timer = setInterval(tick, 250);
    return () => clearInterval(timer);
  });
</script>

<div
  class="panel"
  style:max-width="{PANEL_MAX_WIDTH}px"
  use:glassShape={{ radius: PANEL_RADIUS }}
  use:glassPoke
>
  <span class="title">{title}</span>
  {#if detail}<span class="detail">{detail}</span>{/if}
  <div class="actions">
    <button class="pill" onclick={() => oncancel?.()}>{cancelLabel}</button>
    <button class="pill primary" onclick={() => onconfirm?.()}>{confirmLabel}</button>
  </div>
  <span class="expires">
    {left > 0 ? `Se cancela sola en ${left} s` : "Cancelada"}
  </span>
</div>

<style>
  .panel {
    display: flex;
    flex-direction: column;
    gap: 4px;
    width: 400px;
    padding: 20px 22px 14px;
    border-radius: 26px;
  }

  .title {
    font-size: 16px;
    font-weight: 600;
    line-height: 1.3;
  }

  .detail {
    font-size: 13px;
    line-height: 1.4;
    color: var(--text-secondary);
  }

  .actions {
    display: flex;
    gap: 8px;
    margin-top: 12px;
  }

  .pill {
    flex: 1;
    padding: 10px 18px;
    border: none;
    border-radius: 999px;
    background: var(--control);
    color: inherit;
    font: inherit;
    font-size: 14px;
    cursor: pointer;
    transition: transform 120ms ease;
  }

  .pill:active {
    transform: scale(0.97);
  }

  .primary {
    background: var(--control-active);
    color: var(--text-on-active);
    font-weight: 600;
  }

  .expires {
    margin-top: 8px;
    font-size: 11px;
    text-align: center;
    color: var(--text-tertiary);
  }
</style>
