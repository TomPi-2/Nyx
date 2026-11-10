<!--
  Deslizador con tirador circular (SPEC sección 13). `oninput` llega mientras se arrastra
  (para ver el cambio al momento) y `onchange` al soltar (para guardar).
-->
<script lang="ts">
  interface Props {
    value: number;
    min: number;
    max: number;
    step?: number;
    label?: string;
    oninput?: (value: number) => void;
    onchange?: (value: number) => void;
  }
  let { value, min, max, step = 1, label, oninput, onchange }: Props = $props();

  const percent = $derived(((value - min) / (max - min)) * 100);
</script>

<input
  type="range"
  {min}
  {max}
  {step}
  {value}
  aria-label={label}
  style:--p="{percent}%"
  oninput={(e) => oninput?.(Number(e.currentTarget.value))}
  onchange={(e) => onchange?.(Number(e.currentTarget.value))}
/>

<style>
  input {
    width: 100%;
    height: 6px;
    margin: 10px 0;
    border-radius: 999px;
    background: linear-gradient(
      90deg,
      var(--control-active) 0 var(--p),
      var(--control) var(--p) 100%
    );
    outline: none;
    appearance: none;
    cursor: pointer;
  }

  input::-webkit-slider-thumb {
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: var(--text);
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
    appearance: none;
  }
</style>
