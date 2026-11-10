<!--
  Campo de texto sin contorno sobre `control` (SPEC sección 13). Guarda al pulsar Enter o al
  salir del campo, no en cada tecla (la palabra personalizada se valida en el núcleo).
-->
<script lang="ts">
  interface Props {
    value: string;
    placeholder?: string;
    label?: string;
    maxLength?: number;
    onchange?: (value: string) => void;
  }
  let { value, placeholder = "", label, maxLength = 60, onchange }: Props = $props();

  let draft = $state("");
  let editing = $state(false);

  function commit() {
    editing = false;
    if (draft.trim() !== value) onchange?.(draft.trim());
  }
</script>

<input
  value={editing ? draft : value}
  {placeholder}
  aria-label={label}
  maxlength={maxLength}
  spellcheck="false"
  onfocus={() => {
    draft = value;
    editing = true;
  }}
  oninput={(e) => (draft = e.currentTarget.value)}
  onblur={commit}
  onkeydown={(e) => {
    if (e.key === "Enter") e.currentTarget.blur();
    if (e.key === "Escape") {
      draft = value;
      e.currentTarget.blur();
    }
  }}
/>

<style>
  input {
    width: 100%;
    padding: 9px 14px;
    border: none;
    border-radius: 999px;
    outline: none;
    background: var(--control);
    color: var(--text);
    font: inherit;
    font-size: 13px;
    user-select: text;
  }

  input::placeholder {
    color: var(--text-tertiary);
  }
</style>
