<!--
  Elegir un color entre opciones fijas (Ajustes → Apariencia). Muestras redondeadas, sin
  bordes; la elegida se marca con un anillo de separación (sombra, no borde).
-->
<script lang="ts" generics="T extends string">
  interface Props {
    options: { value: T; label: string; color: string }[];
    value: T;
    label?: string;
    onchange?: (value: T) => void;
  }
  let { options, value, label, onchange }: Props = $props();
</script>

<div class="swatches" role="radiogroup" aria-label={label}>
  {#each options as option (option.value)}
    <button
      role="radio"
      aria-checked={value === option.value}
      aria-label={option.label}
      title={option.label}
      class:on={value === option.value}
      style:background={option.color}
      onclick={() => value !== option.value && onchange?.(option.value)}
    ></button>
  {/each}
</div>

<style>
  .swatches {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    padding: 4px 0 6px;
  }

  button {
    width: 34px;
    height: 34px;
    padding: 0;
    border: none;
    border-radius: 12px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25);
    cursor: pointer;
    transition: transform 140ms ease;
  }

  button:hover {
    transform: scale(1.08);
  }

  /* Anillo: un hueco del color de la tarjeta y luego el control activo. */
  .on {
    box-shadow:
      0 0 0 3px var(--glass-raised),
      0 0 0 5px var(--control-active);
  }
</style>
