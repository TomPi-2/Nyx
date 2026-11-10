<!-- Interruptor estilo iOS (SPEC sección 13): encendido en `control-active`, sin bordes. -->
<script lang="ts">
  interface Props {
    checked: boolean;
    label?: string;
    disabled?: boolean;
    onchange?: (checked: boolean) => void;
  }
  let { checked, label, disabled = false, onchange }: Props = $props();
</script>

<button
  class="toggle"
  class:on={checked}
  role="switch"
  aria-checked={checked}
  aria-label={label}
  {disabled}
  onclick={() => onchange?.(!checked)}
>
  <span class="knob"></span>
</button>

<style>
  .toggle {
    position: relative;
    flex: none;
    width: 46px;
    height: 28px;
    padding: 0;
    border: none;
    border-radius: 999px;
    background: var(--control);
    cursor: pointer;
    transition: background 180ms ease;
  }

  .toggle:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .knob {
    position: absolute;
    top: 3px;
    left: 3px;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    background: var(--text);
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.25);
    transition:
      transform 220ms cubic-bezier(0.34, 1.4, 0.64, 1),
      background 180ms ease;
  }

  .on {
    background: var(--control-active);
  }

  .on .knob {
    transform: translateX(18px);
    background: var(--text-on-active);
  }

  @media (prefers-reduced-motion: reduce) {
    .toggle,
    .knob {
      transition: none;
    }
  }
</style>
