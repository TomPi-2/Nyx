<!--
  Campo de texto (SPEC sección 11): pastilla de cristal en el sitio de la isla.
  Se abre con Win+Alt+N; Enter envía, Esc o hacer clic fuera la cierran.
-->
<script lang="ts">
  import { onMount } from "svelte";
  import { invoke } from "@tauri-apps/api/core";
  import { listen } from "@tauri-apps/api/event";
  import { getCurrentWindow } from "@tauri-apps/api/window";
  import { connectCore, type CoreConnection } from "$lib/core";

  const TOP = 12; // mismo margen que la isla
  const MAX_LENGTH = 2000; // igual que TextInput en core/nyx/bridge/protocol.py

  let text = $state("");
  let shown = $state(false);
  let connected = $state(false);
  let field: HTMLInputElement | undefined = $state();
  let core: CoreConnection | undefined;

  function hide() {
    shown = false;
    text = "";
    void invoke("input_hide");
  }

  function submit() {
    const value = text.trim();
    if (!value) {
      hide();
      return;
    }
    if (core?.send({ type: "text", text: value })) hide();
  }

  function onkeydown(event: KeyboardEvent) {
    if (event.key === "Enter") {
      event.preventDefault();
      submit();
    } else if (event.key === "Escape") {
      event.preventDefault();
      hide();
    }
  }

  onMount(() => {
    core = connectCore(
      () => {},
      (ok) => (connected = ok),
    );
    const offShow = listen("input://show", () => {
      shown = true;
      text = "";
      requestAnimationFrame(() => field?.focus());
    });
    const offFocus = getCurrentWindow().onFocusChanged(({ payload: focused }) => {
      if (!focused && shown) hide();
    });
    return () => {
      core?.close();
      void offShow.then((off) => off());
      void offFocus.then((off) => off());
    };
  });
</script>

<div class="pill" class:shown style:top="{TOP}px">
  <input
    bind:this={field}
    bind:value={text}
    {onkeydown}
    maxlength={MAX_LENGTH}
    placeholder={connected ? "Escribe a Nyx…" : "Nyx aún no está listo"}
    spellcheck="false"
    autocomplete="off"
    aria-label="Escribe a Nyx"
  />
</div>

<style>
  .pill {
    position: absolute;
    left: 50%;
    translate: -50% 0;
    width: 520px;
    height: 52px;
    display: flex;
    align-items: center;
    border-radius: 9999px;
    background: var(--glass-sheen), var(--glass-fallback);
    box-shadow: var(--shadow);
    opacity: 0;
    scale: 0.96;
    filter: blur(6px);
    transition:
      opacity 200ms ease,
      scale 300ms cubic-bezier(0.34, 1.4, 0.64, 1),
      filter 240ms ease;
  }

  .pill.shown {
    opacity: 1;
    scale: 1;
    filter: blur(0);
  }

  input {
    width: 100%;
    height: 100%;
    padding: 0 24px;
    border: none;
    outline: none;
    background: transparent;
    color: var(--text);
    caret-color: var(--text);
    font: inherit;
    font-size: 17px;
    user-select: text;
  }

  input::placeholder {
    color: var(--text-tertiary);
  }

  @media (prefers-reduced-motion: reduce) {
    .pill {
      transition: none;
    }
  }
</style>
