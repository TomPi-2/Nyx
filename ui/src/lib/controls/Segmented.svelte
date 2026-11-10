<!-- Selector en pastilla (SPEC sección 13): la opción elegida en `control-active`. -->
<script lang="ts" generics="T extends string">
  interface Props {
    options: { value: T; label: string }[];
    value: T;
    label?: string;
    compact?: boolean;
    onchange?: (value: T) => void;
  }
  let { options, value, label, compact = false, onchange }: Props = $props();
</script>

<div class="segmented" class:compact role="radiogroup" aria-label={label}>
  {#each options as option (option.value)}
    <button
      role="radio"
      aria-checked={value === option.value}
      class:on={value === option.value}
      onclick={() => value !== option.value && onchange?.(option.value)}
    >
      {option.label}
    </button>
  {/each}
</div>

<style>
  .segmented {
    display: flex;
    gap: 4px;
    padding: 4px;
    border-radius: 999px;
    background: var(--control);
  }

  button {
    flex: 1;
    padding: 7px 12px;
    border: none;
    border-radius: 999px;
    background: transparent;
    color: inherit;
    font: inherit;
    font-size: 13px;
    white-space: nowrap;
    cursor: pointer;
    transition:
      background 160ms ease,
      color 160ms ease;
  }

  .compact button {
    padding: 5px 10px;
    font-size: 12px;
  }

  .on {
    background: var(--control-active);
    color: var(--text-on-active);
  }
</style>
