<!--
  Desplegable propio con el estilo de Ajustes (SPEC sección 13): pastilla sobre `control` y una
  lista en tarjeta redondeada, sin bordes, que aparece como Nyx. El nativo de Windows no se
  puede adaptar a esta identidad.

  La lista se mueve a <body> («portal»): la ventana de Ajustes tiene una animación de escala y,
  dentro de ella, una lista con posición fija se colocaría mal.
-->
<script lang="ts">
  import { tick } from "svelte";
  import { POP_IN_MS, POP_OUT_MS, pop } from "$lib/motion";

  interface Props {
    options: { value: string; label: string }[];
    value: string;
    label?: string;
    onchange?: (value: string) => void;
  }
  let { options, value, label, onchange }: Props = $props();

  const MAX_HEIGHT = 280;
  const MARGIN = 12;

  let open = $state(false);
  let active = $state(0); // opción resaltada (ratón o teclado)
  let trigger: HTMLButtonElement | undefined = $state();
  let list: HTMLDivElement | undefined = $state();
  let place = $state({ left: 0, width: 0, top: 0, bottom: 0, up: false, maxHeight: MAX_HEIGHT });

  const current = $derived(options.find((o) => o.value === value));

  function portal(node: HTMLElement) {
    document.body.appendChild(node);
    return { destroy: () => node.remove() };
  }

  function measure() {
    if (!trigger) return;
    const r = trigger.getBoundingClientRect();
    const below = window.innerHeight - r.bottom - MARGIN;
    const above = r.top - MARGIN;
    const up = below < 180 && above > below;
    place = {
      left: r.left,
      width: r.width,
      top: r.bottom + 6,
      bottom: window.innerHeight - r.top + 6,
      up,
      maxHeight: Math.min(MAX_HEIGHT, up ? above : below),
    };
  }

  async function show() {
    measure();
    active = Math.max(
      0,
      options.findIndex((o) => o.value === value),
    );
    open = true;
    await tick();
    list?.focus();
    list?.querySelector<HTMLElement>(".active")?.scrollIntoView({ block: "nearest" });
  }

  function close(refocus = true) {
    open = false;
    if (refocus) trigger?.focus();
  }

  function choose(next: string) {
    close();
    if (next !== value) onchange?.(next);
  }

  async function move(to: number) {
    active = Math.min(options.length - 1, Math.max(0, to));
    await tick();
    list?.querySelector<HTMLElement>(".active")?.scrollIntoView({ block: "nearest" });
  }

  function onListKey(e: KeyboardEvent) {
    const keys: Record<string, () => void> = {
      ArrowDown: () => void move(active + 1),
      ArrowUp: () => void move(active - 1),
      Home: () => void move(0),
      End: () => void move(options.length - 1),
      Enter: () => choose(options[active].value),
      " ": () => choose(options[active].value),
      Escape: () => close(),
      Tab: () => close(false),
    };
    const action = keys[e.key];
    if (!action) return;
    if (e.key !== "Tab") e.preventDefault();
    action();
  }

  // Abierta: se cierra al pulsar fuera, al desplazar Ajustes o al cambiar el tamaño.
  $effect(() => {
    if (!open) return;
    const outside = (e: PointerEvent) => {
      const target = e.target as Node;
      if (!list?.contains(target) && !trigger?.contains(target)) close(false);
    };
    const away = (e: Event) => {
      if (!list?.contains(e.target as Node)) close(false);
    };
    window.addEventListener("pointerdown", outside, true);
    window.addEventListener("scroll", away, true);
    window.addEventListener("resize", away);
    return () => {
      window.removeEventListener("pointerdown", outside, true);
      window.removeEventListener("scroll", away, true);
      window.removeEventListener("resize", away);
    };
  });
</script>

<button
  class="trigger"
  class:open
  bind:this={trigger}
  aria-haspopup="listbox"
  aria-expanded={open}
  aria-label={label}
  onclick={() => (open ? close() : void show())}
  onkeydown={(e) => {
    if (!open && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
      e.preventDefault();
      void show();
    }
  }}
>
  <span class="current">{current?.label ?? ""}</span>
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
</button>

{#if open}
  <div
    use:portal
    bind:this={list}
    class="list"
    class:up={place.up}
    role="listbox"
    tabindex="-1"
    aria-label={label}
    style:left="{place.left}px"
    style:width="{place.width}px"
    style:top={place.up ? null : `${place.top}px`}
    style:bottom={place.up ? `${place.bottom}px` : null}
    style:max-height="{place.maxHeight}px"
    onkeydown={onListKey}
    in:pop={{ duration: POP_IN_MS }}
    out:pop={{ duration: POP_OUT_MS }}
  >
    {#each options as option, i (option.value)}
      <button
        type="button"
        role="option"
        tabindex="-1"
        aria-selected={option.value === value}
        class:active={i === active}
        class:selected={option.value === value}
        onpointerenter={() => (active = i)}
        onclick={() => choose(option.value)}
      >
        <span>{option.label}</span>
        {#if option.value === value}
          <svg viewBox="0 0 12 12" width="11" height="11" aria-hidden="true">
            <path
              d="M2.5 6.2l2.3 2.3L9.5 3.8"
              fill="none"
              stroke="currentColor"
              stroke-width="1.6"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
        {/if}
      </button>
    {/each}
  </div>
{/if}

<style>
  .trigger {
    display: flex;
    align-items: center;
    gap: 10px;
    width: 100%;
    padding: 9px 14px;
    border: none;
    border-radius: 999px;
    background: var(--control);
    color: var(--text);
    font: inherit;
    font-size: 13px;
    text-align: left;
    cursor: pointer;
  }

  .current {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .trigger svg {
    flex: none;
    color: var(--text-secondary);
    transition: rotate 200ms ease;
  }

  .trigger.open svg {
    rotate: 180deg;
  }

  .list {
    --menu: rgba(44, 44, 46, 0.94);
    position: fixed;
    z-index: 1000;
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 6px;
    border-radius: 18px;
    background: var(--menu);
    backdrop-filter: blur(20px) saturate(1.2);
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.35);
    overflow-y: auto;
    outline: none;
    transform-origin: top center;
  }

  .list.up {
    transform-origin: bottom center;
  }

  @media (prefers-color-scheme: light) {
    .list {
      --menu: rgba(255, 255, 255, 0.95);
      box-shadow: 0 12px 40px rgba(0, 0, 0, 0.14);
    }
  }

  .list button {
    display: flex;
    flex: none;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    border: none;
    border-radius: 12px;
    background: transparent;
    color: var(--text);
    font: inherit;
    font-size: 13px;
    text-align: left;
    cursor: pointer;
  }

  .list button span {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .list button.active {
    background: var(--control);
  }

  .list button.selected {
    font-weight: 600;
  }
</style>
