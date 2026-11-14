<!--
  Muestras de color con el nombre siempre a la vista (primer arranque guiado, 9.10): así se
  pueden elegir por voz («ponte coral»). La elegida se marca como en Ajustes (Swatches.svelte):
  un anillo separado por un hueco, sin bordes, y el nombre en negrita.
-->
<script lang="ts" generics="T extends string">
  interface Props {
    options: { value: T; label: string; color: string }[];
    value: T;
    label: string;
    columns?: number;
    onchange?: (value: T) => void;
  }
  let { options, value, label, columns = 5, onchange }: Props = $props();
</script>

<div class="swatches" role="radiogroup" aria-label={label} style:--cols={columns}>
  {#each options as option (option.value)}
    <button
      role="radio"
      aria-checked={value === option.value}
      class:on={value === option.value}
      onclick={() => value !== option.value && onchange?.(option.value)}
    >
      <i style:background={option.color}></i>
      <span>{option.label}</span>
    </button>
  {/each}
</div>

<style>
  .swatches {
    display: grid;
    grid-template-columns: repeat(var(--cols), 1fr);
    gap: 12px 4px;
  }

  button {
    display: grid;
    justify-items: center;
    gap: 7px;
    padding: 0;
    border: none;
    background: none;
    font: inherit;
    color: var(--text-secondary);
    cursor: pointer;
  }

  i {
    width: 34px;
    height: 34px;
    border-radius: 12px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25);
    transition:
      transform 140ms ease,
      box-shadow 200ms ease;
  }

  button:hover i {
    transform: scale(1.08);
  }

  span {
    font-size: 11.5px;
    line-height: 1.2;
    text-align: center;
    transition: color 200ms ease;
  }

  /* Anillo: un hueco del color del panel y luego el control activo (como en Ajustes). */
  .on i {
    box-shadow:
      0 0 0 3px var(--glass-raised),
      0 0 0 5px var(--control-active);
  }

  .on span {
    color: var(--text);
    font-weight: 600;
  }

  button:focus-visible {
    outline: none;
  }

  button:focus-visible i {
    box-shadow:
      0 0 0 3px var(--glass-raised),
      0 0 0 5px var(--text-tertiary);
  }

  @media (prefers-reduced-motion: reduce) {
    i {
      transition: none;
    }
  }
</style>
