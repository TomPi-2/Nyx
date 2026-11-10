<!--
  Desplegable en pastilla sobre `control`, sin contorno (SPEC sección 13). Para listas que
  pueden ser largas (micrófonos, altavoces); con pocas opciones mejor un Segmented.
-->
<script lang="ts">
  interface Props {
    options: { value: string; label: string }[];
    value: string;
    label?: string;
    onchange?: (value: string) => void;
  }
  let { options, value, label, onchange }: Props = $props();
</script>

<div class="select">
  <select {value} aria-label={label} onchange={(e) => onchange?.(e.currentTarget.value)}>
    {#each options as option (option.value)}
      <option value={option.value}>{option.label}</option>
    {/each}
  </select>
  <svg viewBox="0 0 12 12" width="10" height="10" aria-hidden="true">
    <path
      d="M3 4.5l3 3 3-3"
      fill="none"
      stroke="currentColor"
      stroke-width="1.5"
      stroke-linecap="round"
      stroke-linejoin="round"
    />
  </svg>
</div>

<style>
  .select {
    position: relative;
    display: flex;
    align-items: center;
    width: 100%;
  }

  select {
    width: 100%;
    padding: 9px 36px 9px 14px;
    border: none;
    border-radius: 999px;
    outline: none;
    background: var(--control);
    color: var(--text);
    font: inherit;
    font-size: 13px;
    appearance: none;
    cursor: pointer;
    text-overflow: ellipsis;
  }

  /* La lista desplegable la dibuja Windows: que use el tema de Nyx. */
  option {
    background: #2c2c2e;
    color: #f5f5f7;
  }

  @media (prefers-color-scheme: light) {
    option {
      background: #ffffff;
      color: #1c1c1e;
    }
  }

  svg {
    position: absolute;
    right: 14px;
    color: var(--text-secondary);
    pointer-events: none;
  }
</style>
