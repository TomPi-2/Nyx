<!--
  Campo de texto para escribirle a Nyx (SPEC sección 11), sobre el motor de cristal.
  Empieza como una pastilla de una línea y, si el texto no cabe, crece hacia abajo (hasta
  MAX_LINES; después se desplaza por dentro). Enter envía, Mayús+Enter salta de línea y Esc
  cierra.
-->
<script lang="ts">
  import { glassShape } from "$lib/glass";
  import { PANEL_MAX_WIDTH } from "./layout";

  interface Props {
    value?: string;
    placeholder?: string;
    maxLength?: number;
    disabled?: boolean;
    onsubmit?: (text: string) => void;
    oncancel?: () => void;
    field?: HTMLTextAreaElement;
  }
  let {
    value = $bindable(""),
    placeholder = "Escríbele a Nyx",
    maxLength = 2000,
    disabled = false,
    onsubmit,
    oncancel,
    field = $bindable(),
  }: Props = $props();

  const LINE_HEIGHT = 22; // px, igual que en el CSS
  const MAX_LINES = 6;

  const ready = $derived(value.trim().length > 0 && !disabled);

  // Alto según el contenido: se mide con scrollHeight tras volver a una línea.
  $effect(() => {
    void value;
    if (!field) return;
    field.style.height = "auto";
    field.style.height = `${Math.min(field.scrollHeight, LINE_HEIGHT * MAX_LINES)}px`;
  });

  function onkeydown(event: KeyboardEvent) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (ready) onsubmit?.(value.trim());
    } else if (event.key === "Escape") {
      event.preventDefault();
      oncancel?.();
    }
  }
</script>

<div class="panel" style:width="{PANEL_MAX_WIDTH}px" use:glassShape={{ radius: 28, wobble: 0.7 }}>
  <textarea
    bind:this={field}
    bind:value
    rows="1"
    {placeholder}
    maxlength={maxLength}
    {disabled}
    spellcheck="false"
    autocomplete="off"
    {onkeydown}></textarea>
  <button
    class="send"
    class:ready
    disabled={!ready}
    aria-label="Enviar"
    onclick={() => onsubmit?.(value.trim())}
  >
    <svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true">
      <path
        d="M10 15.5V4.5M5.5 9L10 4.5 14.5 9"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
    </svg>
  </button>
</div>

<style>
  .panel {
    display: flex;
    align-items: flex-end;
    gap: 8px;
    min-height: 56px;
    padding: 8px 8px 8px 22px;
    border-radius: 28px;
  }

  textarea {
    flex: 1;
    min-width: 0;
    /* Una línea centrada en la pastilla de 56 px: (40 - 22) / 2 arriba y abajo. */
    margin: 9px 0;
    padding: 0;
    border: none;
    outline: none;
    resize: none;
    overflow-y: auto;
    background: transparent;
    color: var(--text);
    font: inherit;
    font-size: 16px;
    line-height: 22px;
    caret-color: var(--text);
    user-select: text;
    scrollbar-width: thin;
    scrollbar-color: var(--control) transparent;
  }

  textarea::placeholder {
    color: var(--text-tertiary);
  }

  .send {
    display: grid;
    flex: none;
    place-items: center;
    width: 40px;
    height: 40px;
    border: none;
    border-radius: 50%;
    background: var(--control);
    color: var(--text-tertiary);
    cursor: default;
    transition:
      background 160ms ease,
      color 160ms ease,
      transform 160ms ease;
  }

  .send.ready {
    background: var(--control-active);
    color: var(--text-on-active);
    cursor: pointer;
  }

  .send.ready:active {
    transform: scale(0.94);
  }
</style>
