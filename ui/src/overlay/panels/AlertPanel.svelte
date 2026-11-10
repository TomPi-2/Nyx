<!--
  Aviso (SPEC sección 11): alarmas, temporizadores, recordatorios y acciones diferidas.
  Campana que late despacio, qué es y cuándo, y el botón para pararlo.
-->
<script lang="ts">
  import { glassPoke, glassShape } from "$lib/glass";
  import { PANEL_MAX_WIDTH, PANEL_RADIUS } from "./layout";

  interface Props {
    title: string;
    secondary?: string | null;
    actionLabel?: string;
    onaction?: () => void;
  }
  let { title, secondary = null, actionLabel = "Parar", onaction }: Props = $props();
</script>

<div
  class="panel"
  style:max-width="{PANEL_MAX_WIDTH}px"
  use:glassShape={{ radius: PANEL_RADIUS }}
  use:glassPoke
>
  <span class="bell" aria-hidden="true">
    <svg viewBox="0 0 20 20" width="20" height="20">
      <path
        d="M10 3.2a4.6 4.6 0 0 0-4.6 4.6v2.6L4 13.2h12l-1.4-2.8V7.8A4.6 4.6 0 0 0 10 3.2zM8.2 15.6a1.9 1.9 0 0 0 3.6 0"
        fill="none"
        stroke="currentColor"
        stroke-width="1.6"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
    </svg>
  </span>
  <span class="texts">
    <span class="title">{title}</span>
    {#if secondary}<span class="secondary">{secondary}</span>{/if}
  </span>
  <button class="pill" onclick={() => onaction?.()}>{actionLabel}</button>
</div>

<style>
  .panel {
    display: flex;
    align-items: center;
    gap: 14px;
    min-width: 340px;
    padding: 14px 14px 14px 16px;
    border-radius: 26px;
  }

  .bell {
    display: grid;
    flex: none;
    place-items: center;
    width: 40px;
    height: 40px;
    border-radius: 50%;
    background: var(--glass-raised);
    animation: ring 1.6s ease-in-out infinite;
  }

  @keyframes ring {
    0%,
    100% {
      transform: rotate(0deg);
    }
    10% {
      transform: rotate(-10deg);
    }
    20% {
      transform: rotate(9deg);
    }
    30% {
      transform: rotate(-5deg);
    }
    40% {
      transform: rotate(0deg);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .bell {
      animation: none;
    }
  }

  .texts {
    display: flex;
    flex: 1;
    flex-direction: column;
  }

  .title {
    font-family: "Segoe UI Variable Display", "Segoe UI", system-ui, sans-serif;
    font-size: 20px;
    font-weight: 600;
  }

  .secondary {
    font-size: 13px;
    color: var(--text-secondary);
  }

  .pill {
    flex: none;
    padding: 10px 20px;
    border: none;
    border-radius: 999px;
    background: var(--control-active);
    color: var(--text-on-active);
    font: inherit;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
  }
</style>
