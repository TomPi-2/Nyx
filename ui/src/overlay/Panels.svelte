<!--
  Ventana de los paneles de la isla (SPEC sección 11): respuesta, confirmación, deshacer y
  aviso, sobre el motor de cristal. Va en su propia ventana, debajo de la forma de Nyx con un
  hueco fijo (panels/layout.ts): así Nyx sale siempre en capturas y directos, y nunca se
  tocan. Recibe las burbujas directamente del núcleo (que manda todo a todas las ventanas).
-->
<script lang="ts">
  import { onMount } from "svelte";
  import { invoke } from "@tauri-apps/api/core";
  import { emitTo } from "@tauri-apps/api/event";
  import { sendNotification } from "@tauri-apps/plugin-notification";
  import { connectCore, type CoreConnection } from "$lib/core";
  import { applyAppearance } from "$theme/apply";
  import { DEFAULT_GLASS, edgeLevelToPx, glass, glassFromSettings } from "$lib/glass";
  import type {
    ActionButton,
    BubbleKind,
    LongSection,
    NyxState,
    ServerMessage,
    SetupFlowAction,
    SetupFlowState,
  } from "$lib/protocol";
  import SetupPanel from "../setup/SetupPanel.svelte";
  import AlertPanel from "./panels/AlertPanel.svelte";
  import ConfirmPanel from "./panels/ConfirmPanel.svelte";
  import LongPanel, { type Chunk } from "./panels/LongPanel.svelte";
  import ResponsePanel from "./panels/ResponsePanel.svelte";
  import UndoPanel from "./panels/UndoPanel.svelte";
  import {
    MOVE_EVENT,
    MOVE_IN_MS,
    MOVE_OUT_MS,
    POP_IN_MS,
    POP_OUT_MS,
    type MovePhase,
  } from "$lib/motion";
  import { getCurrentWebviewWindow } from "@tauri-apps/api/webviewWindow";
  import {
    INPUT_EVENT,
    INPUT_MAX_HEIGHT,
    NYX_EVENT,
    PANEL_GAP,
    PANELS_EVENT,
    PANEL_MAX_WIDTH,
    PANEL_MOVE_MS,
    panelTop,
    raisedTop,
    type InputLayout,
    type NyxPresence,
  } from "./panels/layout";

  /** Margen alrededor del panel dentro de la ventana: sombra y ondulación del borde. */
  const PAD = 28;
  /** Alto máximo de un panel (la respuesta larga se desplaza por dentro). */
  const AREA_HEIGHT = 340;
  /** El panel largo (6.28) llega a 480 px y lleva botones debajo. */
  const LONG_AREA_HEIGHT = 520;
  /** El panel largo se cierra solo tras 2 minutos sin tocarlo (con el puntero encima, no). */
  const LONG_IDLE_MS = 120_000;
  /** El panel del primer arranque, con los 19 colores, mide más. */
  const SETUP_AREA_HEIGHT = 560;
  /** Tras la despedida del primer arranque, el panel se queda este rato antes de irse. */
  const SETUP_LINGER_MS = 2500;

  interface Bubble {
    id: number;
    display: string;
    secondary: string | null;
    actions: ActionButton[];
    kind: BubbleKind;
    expiresMs: number | null;
    // Panel largo (v17)
    text: string;
    sections: LongSection[];
    chunks: Chunk[];
    note: string;
    undoAction: string | null;
  }

  let bubble = $state<Bubble | null>(null);
  let leaving = $state(false);
  let connected = $state(false);
  let size = $state(100);
  let edgePx = $state(DEFAULT_GLASS.amplitude);
  let game = $state<{ active: boolean; mode: "off" | "voice" | "normal"; monitor: string }>({
    active: false,
    mode: "voice",
    monitor: "",
  });
  let slot: HTMLDivElement | undefined = $state();
  let core: CoreConnection | undefined;
  let nextId = 0;
  let leaveTimer: ReturnType<typeof setTimeout> | undefined;
  // Sin Nyx en pantalla, el panel sube a ocupar su sitio (panels/layout.ts). Lo dice la
  // ventana de la forma, que es la única que sabe cuándo ha desaparecido del todo.
  let away = $state(true);
  let moving = $state<MovePhase | null>(null);
  let movingTimer: ReturnType<typeof setTimeout> | undefined;
  function setAway(value: boolean) {
    if (value === away) return;
    away = value;
    glass.follow(PANEL_MOVE_MS + 60);
  }

  // «Desactivado»: nada en partida. «Solo voz»: el coordinador de monitores (monitors.rs) la
  // lleva a otro monitor o no la muestra en ninguno.
  const hiddenForGame = $derived(game.active && game.mode === "off");

  // Primer arranque guiado (9.10): mientras dura, su panel va en lugar de las burbujas. Al
  // terminar se queda con la despedida hasta que Nyx acaba de hablar.
  let flow = $state<SetupFlowState | null>(null);
  let status = $state<NyxState>("idle");
  let micLevel = $state(0);
  let lingering = $state(false);
  let lingerTimer: ReturnType<typeof setTimeout> | undefined;
  function onFlow(next: SetupFlowState) {
    if (flow?.active && !next.active) lingering = true;
    if (next.active) lingering = false;
    flow = next;
  }
  $effect(() => {
    clearTimeout(lingerTimer);
    if (lingering && status !== "speaking") {
      lingerTimer = setTimeout(() => (lingering = false), SETUP_LINGER_MS);
    }
  });
  const setupOn = $derived(flow !== null && (flow.active || lingering));
  function sendFlow(action: SetupFlowAction, value?: string | number | boolean | null) {
    core?.send({ type: "setup_flow", action, value: value ?? null });
  }

  const visible = $derived(connected && !hiddenForGame && (bubble !== null || setupOn));

  // Con Nyx, debajo de la forma con el hueco fijo (contando la ondulación del borde); sin
  // Nyx, arriba del todo. La ventana empieza en el borde superior y cubre los dos sitios.
  const lowered = $derived(panelTop(size, edgePx));
  // Con el campo de texto abierto, el panel va debajo de él (con el mismo hueco); si no, en
  // su sitio de siempre: bajo Nyx o, sin Nyx, arriba.
  let input = $state<InputLayout>({ open: false, bottom: 0 });
  const target = $derived(
    input.open
      ? Math.max(away ? 0 : lowered, input.bottom + PANEL_GAP + edgePx)
      : away
        ? raisedTop(size)
        : lowered,
  );
  $effect(() => {
    void target;
    glass.follow(PANEL_MOVE_MS + 60);
  });
  // Al campo de texto: ¿hay un panel en su sitio (arriba sin Nyx, bajo Nyx con ella)?
  // Entonces espera a que baje.
  $effect(() => {
    void emitTo("input", PANELS_EVENT, visible && !input.open);
  });
  $effect(() => {
    void invoke("island_set_size", {
      width: PANEL_MAX_WIDTH + 2 * PAD,
      // Cabe en cualquier sitio: bajo Nyx o bajo el campo de texto con 6 líneas.
      height:
        Math.max(lowered, raisedTop(size) + INPUT_MAX_HEIGHT + PANEL_GAP + edgePx) +
        (setupOn ? SETUP_AREA_HEIGHT : bubble?.kind === "long" ? LONG_AREA_HEIGHT : AREA_HEIGHT) +
        PAD,
      top: 0,
    });
  });

  $effect(() => {
    void invoke("island_set_visible", { visible });
  });

  // Solo los botones (y el panel largo entero, `data-hit`) reciben clics; el resto de la
  // ventana los deja pasar.
  function updateHitRects() {
    const buttons = visible && slot ? [...slot.querySelectorAll("button, [data-hit]")] : [];
    const rects = buttons.map((b) => {
      const r = b.getBoundingClientRect();
      return [r.x, r.y, r.width, r.height];
    });
    void invoke("island_set_hit_rects", { rects });
  }

  $effect(() => {
    void bubble;
    void visible;
    void target;
    void flow;
    requestAnimationFrame(updateHitRects);
    // Tras la animación de entrada o el cambio de sitio.
    const timer = setTimeout(updateHitRects, Math.max(POP_IN_MS, PANEL_MOVE_MS) + 50);
    return () => clearTimeout(timer);
  });

  /** El tipo lo dice el núcleo (v7); si no, se deduce de los botones. */
  function kindOf(msg: Extract<ServerMessage, { type: "bubble" }>): BubbleKind {
    if (msg.kind && msg.kind !== "response") return msg.kind;
    if (msg.alert) return "alert";
    if (msg.actions.length >= 2) return "confirm";
    if (msg.actions.length === 1) return "undo";
    return "response";
  }

  function show(msg: Extract<ServerMessage, { type: "bubble" }>) {
    clearTimeout(leaveTimer);
    leaving = false;
    bubble = {
      id: ++nextId,
      display: msg.display,
      secondary: msg.secondary,
      actions: msg.actions,
      kind: kindOf(msg),
      expiresMs:
        msg.expires_s !== null && msg.expires_s !== undefined ? msg.expires_s * 1000 : null,
      text: msg.text ?? "",
      sections: msg.sections ?? [],
      chunks: [],
      note: "",
      undoAction: null,
    };
    lastActivity = performance.now();
    glass.poke();
    glass.follow(POP_IN_MS + 80);
  }

  // --- panel largo (6.28) ---

  /** Una frase que empieza a sonar: se escribe al ritmo de su audio. */
  function addChunk(text: string, durationS: number) {
    if (bubble?.kind !== "long") return;
    const chunk: Chunk = { text, durationMs: durationS * 1000, at: performance.now() };
    bubble = { ...bubble, chunks: [...bubble.chunks, chunk] };
    lastActivity = performance.now();
    glass.follow(400);
  }

  function setNote(text: string, undoAction: string | null) {
    if (bubble?.kind !== "long") return;
    bubble = { ...bubble, note: text, undoAction };
    lastActivity = performance.now();
  }

  function longAction(id: string) {
    lastActivity = performance.now();
    core?.send({ type: "action", id });
  }

  // Se cierra solo tras 2 minutos sin tocarlo; con el puntero encima, el tiempo no corre.
  let lastActivity = performance.now();
  let pointerInside = false;
  function onPointer(inside: boolean) {
    pointerInside = inside;
    lastActivity = performance.now();
  }
  $effect(() => {
    if (bubble?.kind !== "long") return;
    const timer = setInterval(() => {
      if (pointerInside) lastActivity = performance.now();
      else if (performance.now() - lastActivity > LONG_IDLE_MS) longAction("long-timeout");
    }, 5000);
    return () => clearInterval(timer);
  });

  // El panel largo crece mientras se escribe: la zona que recibe el ratón crece con él.
  $effect(() => {
    if (!slot) return;
    const observer = new ResizeObserver(() => requestAnimationFrame(updateHitRects));
    observer.observe(slot);
    return () => observer.disconnect();
  });

  function hide() {
    if (!bubble || leaving) return;
    leaving = true;
    glass.follow(POP_OUT_MS + 40);
    leaveTimer = setTimeout(() => {
      bubble = null;
      leaving = false;
    }, POP_OUT_MS);
  }

  function choose(id: string) {
    core?.send({ type: "action", id });
    if (bubble) bubble = { ...bubble, actions: [] }; // evita el doble clic
  }

  function handle(msg: ServerMessage) {
    switch (msg.type) {
      case "welcome":
        size = msg.indicator_size ?? 100;
        applyAppearance(msg);
        if (msg.glass) {
          edgePx = edgeLevelToPx(msg.glass.edge);
          glass.set(glassFromSettings(msg.glass, msg.panel_tint));
        }
        break;
      case "settings":
        // Cambios desde Ajustes: se aplican al momento.
        size = msg.data.appearance.indicator_size;
        edgePx = edgeLevelToPx(msg.data.appearance.glass.edge);
        glass.set(glassFromSettings(msg.data.appearance.glass, msg.data.appearance.panel_tint));
        applyAppearance(msg.data.appearance);
        break;
      case "bubble":
        if (msg.alert) {
          // Alarmas: también en el centro de notificaciones, por si no se mira la pantalla.
          sendNotification({ title: msg.display, body: msg.secondary ?? "" });
        }
        show(msg);
        break;
      case "reading":
        addChunk(msg.text, msg.duration_s);
        break;
      case "panel_note":
        setNote(msg.text, msg.undo_action);
        break;
      case "bubble_hide":
        hide();
        break;
      case "state":
        status = msg.state;
        break;
      case "mic_level":
        micLevel = msg.rms;
        break;
      case "setup_flow_state":
        onFlow(msg.state);
        glass.follow(POP_IN_MS + 80);
        break;
      case "game":
        game = { active: msg.active, mode: msg.mode, monitor: msg.monitor ?? "" };
        // En partida el cristal pasa a Bajo sin excepción (nunca se captura con un juego).
        glass.setGame(msg.active);
        break;
    }
  }

  const primary = $derived(bubble?.actions.find((a) => a.primary) ?? bubble?.actions[0]);
  const secondaryAction = $derived(bubble?.actions.find((a) => a !== primary));

  onMount(() => {
    void glass.attach();
    const connection = connectCore(handle, (ok) => {
      connected = ok;
      if (!ok) bubble = null;
    });
    core = connection;
    const offInput = getCurrentWebviewWindow().listen<InputLayout>(
      INPUT_EVENT,
      (e) => (input = e.payload),
    );
    // Cambio de monitor estando visible: se encoge aquí y aparece allí (island.rs).
    const offMove = getCurrentWebviewWindow().listen<MovePhase>(MOVE_EVENT, (e) => {
      clearTimeout(movingTimer);
      moving = e.payload;
      glass.follow((e.payload === "out" ? MOVE_OUT_MS : MOVE_IN_MS) + 60);
      if (e.payload === "in") movingTimer = setTimeout(() => (moving = null), MOVE_IN_MS);
    });
    const offNyx = getCurrentWebviewWindow().listen<NyxPresence>(NYX_EVENT, (e) =>
      setAway(e.payload === "gone"),
    );
    return () => {
      connection.close();
      void offNyx.then((off) => off());
      void offInput.then((off) => off());
      void offMove.then((off) => off());
      glass.detach();
    };
  });
</script>

<div
  class="slot"
  class:move-out={moving === "out"}
  class:move-in={moving === "in"}
  style:top="0px"
  style:translate="0 {target}px"
  style:--move="{PANEL_MOVE_MS}ms"
  bind:this={slot}
>
  {#if setupOn && flow}
    <div class="pop pop-in">
      <SetupPanel
        {flow}
        speaking={status === "speaking"}
        {micLevel}
        closing={!flow.active}
        send={sendFlow}
      />
    </div>
  {:else if bubble}
    {#key bubble.id}
      <!-- Aparece y se va como la forma de Nyx (lib/motion.ts): cristal y texto a la vez. -->
      <div class="pop" class:pop-in={!leaving} class:pop-out={leaving}>
        {#if bubble.kind === "confirm"}
          <ConfirmPanel
            title={bubble.display}
            detail={bubble.secondary}
            confirmLabel={primary?.label}
            cancelLabel={secondaryAction?.label}
            expiresMs={bubble.expiresMs ?? 15000}
            onconfirm={() => primary && choose(primary.id)}
            oncancel={() => secondaryAction && choose(secondaryAction.id)}
          />
        {:else if bubble.kind === "undo"}
          <UndoPanel
            text={bubble.display}
            secondary={bubble.secondary}
            undoLabel={primary?.label}
            durationMs={bubble.expiresMs ?? 30000}
            onundo={() => primary && choose(primary.id)}
          />
        {:else if bubble.kind === "alert"}
          <AlertPanel
            title={bubble.display}
            secondary={bubble.secondary}
            actionLabel={primary?.label ?? null}
            onaction={() => primary && choose(primary.id)}
          />
        {:else if bubble.kind === "long"}
          <div
            class="long-wrap"
            role="presentation"
            onpointerenter={() => onPointer(true)}
            onpointerleave={() => onPointer(false)}
            onwheel={() => (lastActivity = performance.now())}
          >
            <LongPanel
              title={bubble.display}
              meta={bubble.secondary}
              text={bubble.text}
              sections={bubble.sections}
              chunks={bubble.chunks}
              note={bubble.note}
              undoAction={bubble.undoAction}
              onaction={longAction}
            />
          </div>
        {:else}
          <ResponsePanel display={bubble.display} secondary={bubble.secondary} />
        {/if}
      </div>
    {/key}
  {/if}
</div>

<style>
  .slot {
    position: absolute;
    left: 0;
    right: 0;
    display: flex;
    justify-content: center;
    transition: translate var(--move) cubic-bezier(0.32, 0.72, 0, 1);
  }

  .pop {
    display: flex;
    justify-content: center;
    transform-origin: center;
  }

  @media (prefers-reduced-motion: reduce) {
    .slot {
      transition: none;
    }
  }
</style>
