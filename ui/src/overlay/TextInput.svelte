<!--
  Campo de texto (SPEC sección 11): pastilla sobre el motor de cristal en el sitio de la isla.
  Nunca tapa a Nyx ni a un panel (panels/layout.ts): sin Nyx, donde empieza su cuadrado; con
  Nyx, debajo. Se abre con Win+Alt+N; crece hacia abajo si el texto no cabe. Enter envía,
  Mayús+Enter salta de línea, Esc o hacer clic fuera la cierran.
-->
<script lang="ts">
  import { onMount } from "svelte";
  import { invoke } from "@tauri-apps/api/core";
  import { emitTo, listen } from "@tauri-apps/api/event";
  import { getCurrentWindow } from "@tauri-apps/api/window";
  import { connectCore, type CoreConnection } from "$lib/core";
  import { applyAppearance } from "$theme/apply";
  import { DEFAULT_GLASS, edgeLevelToPx, glass, glassFromSettings } from "$lib/glass";
  import { POP_IN_MS, POP_OUT_MS } from "$lib/motion";
  import type { ServerMessage } from "$lib/protocol";
  import InputPanel from "./panels/InputPanel.svelte";
  import {
    INPUT_EVENT,
    INPUT_MAX_HEIGHT,
    NYX_EVENT,
    PANEL_MOVE_MS,
    PANELS_EVENT,
    panelTop,
    raisedTop,
    type InputLayout,
    type NyxPresence,
  } from "./panels/layout";

  const MAX_LENGTH = 2000; // igual que TextInput en core/nyx/bridge/protocol.py
  /** Margen bajo el campo más largo: sombra y ondulación del borde. */
  const PAD = 28;

  let text = $state("");
  // hidden → (wait) → in (aparece) → out (se encoge) → hidden (se oculta la ventana).
  // «wait»: había un panel arriba, en su sitio; se espera a que baje para no pisarlo.
  let phase = $state<"hidden" | "wait" | "in" | "out">("hidden");
  let panelRaised = false;
  let height = $state(56); // alto del campo (crece al escribir)
  let connected = $state(false);
  let size = $state(100); // lado de la forma de Nyx: el campo va donde empieza su cuadrado
  let edgePx = $state(DEFAULT_GLASS.amplitude);
  /** Nyx a la vista (lo dice la isla): entonces el campo va debajo de ella. */
  let nyxHere = $state(false);
  let slotEl: HTMLDivElement | undefined = $state();
  const top = $derived(nyxHere ? panelTop(size, edgePx) : raisedTop(size));
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
    const layout: InputLayout = { open: phase !== "hidden", bottom: top + height };
    void emitTo("panels", INPUT_EVENT, layout);
    void emitTo("island", INPUT_EVENT, layout);
  });

  // La ventana cubre los dos sitios (sin Nyx y bajo Nyx) con el campo en su alto máximo.
  $effect(() => {
    void invoke("input_set_height", { height: panelTop(size, edgePx) + INPUT_MAX_HEIGHT + PAD });
  });

  // Al cambiar de sitio (Nyx llega o se va) el cristal sigue al campo.
  $effect(() => {
    void top;
    glass.follow(PANEL_MOVE_MS + 60);
  });

  /** Clic en la parte transparente de la ventana: cuenta como clic fuera. */
  function outside(e: PointerEvent) {
    if (slotEl && !slotEl.contains(e.target as Node)) hide();
  }

  function handle(msg: ServerMessage) {
    if (msg.type === "welcome") {
      size = msg.indicator_size ?? 100;
      if (msg.glass) {
        edgePx = edgeLevelToPx(msg.glass.edge);
        glass.set(glassFromSettings(msg.glass, msg.panel_tint));
      }
      applyAppearance(msg);
    }
    if (msg.type === "settings") {
      size = msg.data.appearance.indicator_size;
      edgePx = edgeLevelToPx(msg.data.appearance.glass.edge);
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
    const offNyx = getCurrentWindow().listen<NyxPresence>(NYX_EVENT, (e) => {
      nyxHere = e.payload === "coming";
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
      void offNyx.then((off) => off());
    };
  });
</script>

<svelte:window onpointerdown={outside} />

<div
  bind:this={slotEl}
  class="slot"
  class:hidden={phase === "hidden" || phase === "wait"}
  class:pop-in={phase === "in"}
  class:pop-out={phase === "out"}
  style:top="0px"
  style:translate="0 {top}px"
  style:--move="{PANEL_MOVE_MS}ms"
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
    /* Baja o sube con Nyx, igual que los paneles. */
    transition: translate var(--move) cubic-bezier(0.32, 0.72, 0, 1);
  }

  @media (prefers-reduced-motion: reduce) {
    .slot {
      transition: none;
    }
  }

  .hidden {
    scale: 0;
  }
</style>
