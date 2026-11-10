<!--
  Campo de texto (SPEC sección 11): pastilla sobre el motor de cristal en el sitio de la isla.
  Se abre con Win+Alt+N; crece hacia abajo si el texto no cabe. Enter envía, Mayús+Enter
  salta de línea, Esc o hacer clic fuera la cierran.
-->
<script lang="ts">
  import { onMount } from "svelte";
  import { invoke } from "@tauri-apps/api/core";
  import { listen } from "@tauri-apps/api/event";
  import { getCurrentWindow } from "@tauri-apps/api/window";
  import { connectCore, type CoreConnection } from "$lib/core";
  import { glass, glassFromSettings } from "$lib/glass";
  import type { ServerMessage } from "$lib/protocol";
  import InputPanel from "./panels/InputPanel.svelte";
  import { SHAPE_TOP } from "./panels/layout";

  const MAX_LENGTH = 2000; // igual que TextInput en core/nyx/bridge/protocol.py
  const ANIM_MS = 300;

  let text = $state("");
  let shown = $state(false);
  let connected = $state(false);
  let field: HTMLTextAreaElement | undefined = $state();
  let core: CoreConnection | undefined;

  function hide() {
    shown = false;
    text = "";
    void invoke("input_hide");
  }

  function submit(value: string) {
    if (!value) {
      hide();
      return;
    }
    if (core?.send({ type: "text", text: value })) hide();
  }

  function handle(msg: ServerMessage) {
    if (msg.type === "welcome" && msg.glass) glass.set(glassFromSettings(msg.glass));
    if (msg.type === "settings") glass.set(glassFromSettings(msg.data.appearance.glass));
    // En partida el cristal pasa a Bajo sin excepción.
    if (msg.type === "game") glass.setGame(msg.active);
  }

  onMount(() => {
    void glass.attach();
    core = connectCore(handle, (ok) => (connected = ok));
    const offShow = listen("input://show", () => {
      shown = true;
      text = "";
      glass.poke();
      glass.follow(ANIM_MS);
      requestAnimationFrame(() => field?.focus());
    });
    const offFocus = getCurrentWindow().onFocusChanged(({ payload: focused }) => {
      if (!focused && shown) hide();
    });
    return () => {
      core?.close();
      glass.detach();
      void offShow.then((off) => off());
      void offFocus.then((off) => off());
    };
  });
</script>

<div class="slot" class:shown style:top="{SHAPE_TOP}px">
  <InputPanel
    bind:value={text}
    bind:field
    maxLength={MAX_LENGTH}
    placeholder={connected ? "Escríbele a Nyx" : "Nyx aún no está listo"}
    disabled={!connected}
    onsubmit={submit}
    oncancel={hide}
  />
</div>

<style>
  .slot {
    position: absolute;
    left: 50%;
    translate: -50% 0;
    transform-origin: top center;
    opacity: 0;
    scale: 0.96;
    filter: blur(6px);
    transition:
      opacity 200ms ease,
      scale 300ms cubic-bezier(0.34, 1.4, 0.64, 1),
      filter 240ms ease;
  }

  .slot.shown {
    opacity: 1;
    scale: 1;
    filter: blur(0);
  }

  @media (prefers-reduced-motion: reduce) {
    .slot {
      transition: none;
    }
  }
</style>
