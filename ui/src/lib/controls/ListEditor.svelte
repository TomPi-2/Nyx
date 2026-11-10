<!--
  Lista de textos cortos en pastillas (por ejemplo, ejecutables de juegos): × para quitar y
  un campo sin contorno sobre `control` para añadir (Enter).
-->
<script lang="ts">
  interface Props {
    items: string[];
    placeholder?: string;
    label?: string;
    /** Normaliza lo escrito (minúsculas, sin espacios…); vacío = no se añade. */
    normalize?: (text: string) => string;
    onchange?: (items: string[]) => void;
  }
  let {
    items,
    placeholder = "Añadir",
    label,
    normalize = (t) => t.trim(),
    onchange,
  }: Props = $props();

  let draft = $state("");

  function add() {
    const value = normalize(draft);
    draft = "";
    if (!value || items.includes(value)) return;
    onchange?.([...items, value]);
  }

  function remove(item: string) {
    onchange?.(items.filter((i) => i !== item));
  }
</script>

<div class="list" aria-label={label}>
  {#each items as item (item)}
    <span class="chip">
      {item}
      <button aria-label={`Quitar ${item}`} onclick={() => remove(item)}>
        <svg viewBox="0 0 12 12" width="10" height="10" aria-hidden="true">
          <path
            d="M3 3l6 6M9 3l-6 6"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
          />
        </svg>
      </button>
    </span>
  {/each}
  <input
    bind:value={draft}
    {placeholder}
    spellcheck="false"
    onkeydown={(e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        add();
      }
    }}
    onblur={add}
  />
</div>

<style>
  .list {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    padding: 2px 0 4px;
  }

  .chip {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 5px 6px 5px 12px;
    border-radius: 999px;
    background: var(--control);
    font-size: 13px;
  }

  .chip button {
    display: grid;
    place-items: center;
    width: 20px;
    height: 20px;
    padding: 0;
    border: none;
    border-radius: 50%;
    background: transparent;
    color: var(--text-secondary);
    cursor: pointer;
  }

  .chip button:hover {
    background: var(--control);
    color: var(--text);
  }

  input {
    flex: 1;
    min-width: 140px;
    padding: 6px 12px;
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
