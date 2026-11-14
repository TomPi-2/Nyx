<!--
  Deslizador con tirador circular (SPEC sección 13). `oninput` llega mientras se arrastra
  (para ver el cambio al momento) y `onchange` al soltar (para guardar). Con `bubble`, mientras
  se arrastra sale encima del tirador una etiqueta con el valor (estilo de lib/tooltip.ts).
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
    bubble?: (value: number) => string;
  }
  let { value, min, max, step = 1, label, oninput, onchange, bubble }: Props = $props();

  const percent = $derived(((value - min) / (max - min)) * 100);
  let dragging = $state(false);
</script>

<div class="slider" data-hit style:--p="{percent}%" style:--f={percent / 100}>
  <input
    type="range"
    {min}
    {max}
    {step}
    {value}
    aria-label={label}
    onpointerdown={() => (dragging = true)}
    onpointerup={() => (dragging = false)}
    onblur={() => (dragging = false)}
    oninput={(e) => oninput?.(Number(e.currentTarget.value))}
    onchange={(e) => {
      dragging = false;
      onchange?.(Number(e.currentTarget.value));
    }}
  />
  {#if bubble}
    <span class="bubble nyx-tooltip" class:on={dragging} aria-hidden="true">{bubble(value)}</span>
  {/if}
</div>

<style>
  .slider {
    position: relative;
  }

  /* Encima del centro del tirador (22 px): 11 px + la parte recorrida del resto. */
  .bubble {
    position: absolute;
    left: calc(11px + (100% - 22px) * var(--f));
    top: -26px;
    translate: -50% 0;
    transform-origin: 50% 100%;
  }

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

  /* El tirador crece un poco al pasar el ratón y algo más al arrastrarlo (con muelle). */
  input::-webkit-slider-thumb {
    width: 22px;
    height: 22px;
    border-radius: 50%;
    background: var(--text);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.32);
    appearance: none;
    transition:
      transform 200ms cubic-bezier(0.3, 1.6, 0.5, 1),
      box-shadow 200ms ease;
  }

  input:hover::-webkit-slider-thumb {
    transform: scale(1.1);
  }

  input:active::-webkit-slider-thumb {
    transform: scale(1.22);
  }

  input:focus-visible::-webkit-slider-thumb {
    box-shadow:
      0 0 0 4px var(--control),
      0 2px 8px rgba(0, 0, 0, 0.32);
  }

  @media (prefers-reduced-motion: reduce) {
    input::-webkit-slider-thumb {
      transition: none;
    }
  }
</style>
