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
  import { POP_IN_MS, POP_OUT_MS } from "$lib/motion";
  import type { ServerMessage } from "$lib/protocol";
  import InputPanel from "./panels/InputPanel.svelte";
  import { raisedTop } from "./panels/layout";

  const MAX_LENGTH = 2000; // igual que TextInput en core/nyx/bridge/protocol.py

  let text = $state("");
  // hidden → in (aparece) → out (se encoge) → hidden (se oculta la ventana).
  let phase = $state<"hidden" | "in" | "out">("hidden");
  let connected = $state(false);
  let size = $state(100); // lado de la forma de Nyx: el campo va donde empieza su cuadrado
  let field: HTMLTextAreaElement | undefined = $state();
  let core: CoreConnection | undefined;
  let hideTimer: ReturnType<typeof setTimeout> | undefined;

  /** Se encoge como Nyx al irse y, al terminar, se oculta la ventana. */
  function hide() {
    if (phase !== "in") return;
    phase = "out";
    glass.follow(POP_OUT_MS + 40);
    hideTimer = setTimeout(() => {
      phase = "hidden";
      text = "";
      void invoke("input_hide");
    }, POP_OUT_MS);
  }

  function submit(value: string) {
    if (!value) {
      hide();
      return;
    }
    if (core?.send({ type: "text", text: value })) hide();
  }

  function handle(msg: ServerMessage) {
    if (msg.type === "welcome") {
      size = msg.indicator_size ?? 100;
      if (msg.glass) glass.set(glassFromSettings(msg.glass));
    }
    if (msg.type === "settings") {
      size = msg.data.appearance.indicator_size;
      glass.set(glassFromSettings(msg.data.appearance.glass));
    }
    // En partida el cristal pasa a Bajo sin excepción.
    if (msg.type === "game") glass.setGame(msg.active);
  }

  onMount(() => {
    void glass.attach();
    core = connectCore(handle, (ok) => (connected = ok));
    const offShow = listen("input://show", () => {
      clearTimeout(hideTimer);
      if (phase !== "in") text = "";
      phase = "in";
      glass.poke();
      glass.follow(POP_IN_MS + 60);
      requestAnimationFrame(() => field?.focus());
    });
    const offFocus = getCurrentWindow().onFocusChanged(({ payload: focused }) => {
      if (!focused) hide();
    });
    return () => {
      core?.close();
      glass.detach();
      void offShow.then((off) => off());
      void offFocus.then((off) => off());
    };
  });
</script>

<div
  class="slot"
  class:hidden={phase === "hidden"}
  class:pop-in={phase === "in"}
  class:pop-out={phase === "out"}
  style:top="{raisedTop(size)}px"
>
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
    margin-left: -260px; /* la mitad del ancho del campo (PANEL_MAX_WIDTH) */
    transform-origin: center;
  }

  .hidden {
    scale: 0;
  }
</style>
