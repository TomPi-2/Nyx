<!--
  Campo de texto (SPEC sección 11): pastilla sobre el motor de cristal en el sitio de la isla.
  Se abre con Win+Alt+N; crece hacia abajo si el texto no cabe. Enter envía, Mayús+Enter
  salta de línea, Esc o hacer clic fuera la cierran.
-->
<script lang="ts">
  import { onMount } from "svelte";
  import { invoke } from "@tauri-apps/api/core";
  import { emitTo, listen } from "@tauri-apps/api/event";
  import { getCurrentWindow } from "@tauri-apps/api/window";
  import { connectCore, type CoreConnection } from "$lib/core";
  import { applyAppearance } from "$theme/apply";
  import { glass, glassFromSettings } from "$lib/glass";
  import { POP_IN_MS, POP_OUT_MS } from "$lib/motion";
  import type { ServerMessage } from "$lib/protocol";
  import InputPanel from "./panels/InputPanel.svelte";
  import {
    INPUT_EVENT,
    PANEL_MOVE_MS,
    PANELS_EVENT,
    raisedTop,
    type InputLayout,
  } from "./panels/layout";

  const MAX_LENGTH = 2000; // igual que TextInput en core/nyx/bridge/protocol.py

  let text = $state("");
  // hidden → (wait) → in (aparece) → out (se encoge) → hidden (se oculta la ventana).
  // «wait»: había un panel arriba, en su sitio; se espera a que baje para no pisarlo.
  let phase = $state<"hidden" | "wait" | "in" | "out">("hidden");
  let panelRaised = false;
  let height = $state(56); // alto del campo (crece al escribir)
  let connected = $state(false);
  let size = $state(100); // lado de la forma de Nyx: el campo va donde empieza su cuadrado
  let field: HTMLTextAreaElement | undefined = $state();
  let core: CoreConnection | undefined;
  let hideTimer: ReturnType<typeof setTimeout> | undefined;

  /** Se encoge como Nyx al irse y, al terminar, se oculta la ventana. */
  function hide() {
    if (phase === "wait") {
      clearTimeout(hideTimer);
      phase = "hidden";
      void invoke("input_hide");
      return;
    }
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

  // A los paneles: si el campo está (o va a estar) y dónde acaba, para ponerse debajo. Hasta
  // que no se oculta del todo no se dice que se ha ido: si no, el panel subiría encima.
  $effect(() => {
    const layout: InputLayout = { open: phase !== "hidden", bottom: raisedTop(size) + height };
    void emitTo("panels", INPUT_EVENT, layout);
  });

  function handle(msg: ServerMessage) {
    if (msg.type === "welcome") {
      size = msg.indicator_size ?? 100;
      if (msg.glass) glass.set(glassFromSettings(msg.glass, msg.panel_tint));
      applyAppearance(msg);
    }
    if (msg.type === "settings") {
      size = msg.data.appearance.indicator_size;
      glass.set(glassFromSettings(msg.data.appearance.glass, msg.data.appearance.panel_tint));
      applyAppearance(msg.data.appearance);
    }
    // En partida el cristal pasa a Bajo sin excepción.
    if (msg.type === "game") glass.setGame(msg.active);
  }

  onMount(() => {
    void glass.attach();
    core = connectCore(handle, (ok) => (connected = ok));
    const appear = () => {
      phase = "in";
      glass.poke();
      glass.follow(POP_IN_MS + 60);
    };
    const offShow = listen("input://show", () => {
      clearTimeout(hideTimer);
      if (phase === "in" || phase === "wait") {
        requestAnimationFrame(() => field?.focus());
        return;
      }
      text = "";
      if (panelRaised) {
        // El panel baja primero (ya se le ha avisado: phase ≠ hidden) y luego aparece el campo.
        phase = "wait";
        hideTimer = setTimeout(appear, PANEL_MOVE_MS);
      } else {
        appear();
      }
      // Se puede escribir ya, aunque el campo esté esperando a aparecer.
      requestAnimationFrame(() => field?.focus());
    });
    const offRaised = getCurrentWindow().listen<boolean>(PANELS_EVENT, (e) => {
      panelRaised = e.payload;
    });
    const offFocus = getCurrentWindow().onFocusChanged(({ payload: focused }) => {
      if (!focused) hide();
    });
    return () => {
      core?.close();
      glass.detach();
      void offShow.then((off) => off());
      void offFocus.then((off) => off());
      void offRaised.then((off) => off());
    };
  });
</script>

<div
  class="slot"
  class:hidden={phase === "hidden" || phase === "wait"}
  class:pop-in={phase === "in"}
  class:pop-out={phase === "out"}
  style:top="{raisedTop(size)}px"
>
  <div bind:clientHeight={height}>
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
