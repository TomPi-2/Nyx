<!--
  Ventana de los paneles de la isla (SPEC sección 11): respuesta, confirmación, deshacer y
  aviso, sobre el motor de cristal. Va en su propia ventana, debajo de la forma de Nyx con un
  hueco fijo (panels/layout.ts): así Nyx sale siempre en capturas y directos, y nunca se
  tocan. Recibe las burbujas directamente del núcleo (que manda todo a todas las ventanas).
-->
<script lang="ts">
  import { onMount } from "svelte";
  import { invoke } from "@tauri-apps/api/core";
  import { sendNotification } from "@tauri-apps/plugin-notification";
  import { connectCore, type CoreConnection } from "$lib/core";
  import { DEFAULT_GLASS, edgeLevelToPx, glass, glassFromSettings } from "$lib/glass";
  import type { ActionButton, BubbleKind, ServerMessage } from "$lib/protocol";
  import AlertPanel from "./panels/AlertPanel.svelte";
  import ConfirmPanel from "./panels/ConfirmPanel.svelte";
  import ResponsePanel from "./panels/ResponsePanel.svelte";
  import UndoPanel from "./panels/UndoPanel.svelte";
  import { PANEL_MAX_WIDTH, panelTop } from "./panels/layout";

  /** Margen alrededor del panel dentro de la ventana: sombra y ondulación del borde. */
  const PAD = 28;
  /** Alto máximo de un panel (la respuesta larga se desplaza por dentro). */
  const AREA_HEIGHT = 340;
  const ANIM_MS = 320;

  interface Bubble {
    id: number;
    display: string;
    secondary: string | null;
    actions: ActionButton[];
    kind: BubbleKind;
    expiresMs: number | null;
  }

  let bubble = $state<Bubble | null>(null);
  let leaving = $state(false);
  let connected = $state(false);
  let size = $state(100);
  let edgePx = $state(DEFAULT_GLASS.amplitude);
  let game = $state<{ active: boolean; mode: "off" | "voice" | "normal" }>({
    active: false,
    mode: "voice",
  });
  let slot: HTMLDivElement | undefined = $state();
  let core: CoreConnection | undefined;
  let nextId = 0;
  let leaveTimer: ReturnType<typeof setTimeout> | undefined;

  const hiddenForGame = $derived(game.active && game.mode !== "normal");
  const visible = $derived(connected && !hiddenForGame && bubble !== null);

  // Debajo de la forma de Nyx con el hueco fijo, contando la ondulación del borde.
  $effect(() => {
    void invoke("island_set_size", {
      width: PANEL_MAX_WIDTH + 2 * PAD,
      height: AREA_HEIGHT + 2 * PAD,
      top: panelTop(size, edgePx) - PAD,
    });
  });

  $effect(() => {
    void invoke("island_set_visible", { visible });
  });

  // Solo los botones reciben clics; el resto de la ventana los deja pasar.
  function updateHitRects() {
    const buttons = visible && slot ? [...slot.querySelectorAll("button")] : [];
    const rects = buttons.map((b) => {
      const r = b.getBoundingClientRect();
      return [r.x, r.y, r.width, r.height];
    });
    void invoke("island_set_hit_rects", { rects });
  }

  $effect(() => {
    void bubble;
    void visible;
    requestAnimationFrame(updateHitRects);
    const timer = setTimeout(updateHitRects, ANIM_MS + 50); // tras la animación de entrada
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
    };
    glass.poke();
    glass.follow(ANIM_MS + 80);
  }

  function hide() {
    if (!bubble || leaving) return;
    leaving = true;
    glass.follow(ANIM_MS);
    leaveTimer = setTimeout(() => {
      bubble = null;
      leaving = false;
    }, ANIM_MS);
  }

  function choose(id: string) {
    core?.send({ type: "action", id });
    if (bubble) bubble = { ...bubble, actions: [] }; // evita el doble clic
  }

  function handle(msg: ServerMessage) {
    switch (msg.type) {
      case "welcome":
        size = msg.indicator_size ?? 100;
        if (msg.glass) {
          edgePx = edgeLevelToPx(msg.glass.edge);
          glass.set(glassFromSettings(msg.glass));
        }
        break;
      case "bubble":
        if (msg.alert) {
          // Alarmas: también en el centro de notificaciones, por si no se mira la pantalla.
          sendNotification({ title: msg.display, body: msg.secondary ?? "" });
        }
        show(msg);
        break;
      case "bubble_hide":
        hide();
        break;
      case "game":
        game = { active: msg.active, mode: msg.mode };
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
    return () => {
      connection.close();
      glass.detach();
    };
  });
</script>

<div class="slot" class:leaving style:top="{PAD}px" bind:this={slot}>
  {#if bubble}
    {#key bubble.id}
      <div class="enter">
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
    transform-origin: top center;
    transition:
      opacity 220ms ease,
      scale 260ms ease,
      filter 220ms ease;
  }

  /* Aparecer: escala 0,96 → 1 y desenfoque → nítido (SPEC sección 11). */
  .enter {
    display: flex;
    justify-content: center;
    transform-origin: top center;
    animation: enter 320ms cubic-bezier(0.34, 1.4, 0.64, 1);
  }

  @keyframes enter {
    from {
      opacity: 0;
      scale: 0.96;
      filter: blur(6px);
    }
  }

  .leaving {
    opacity: 0;
    scale: 0.96;
    filter: blur(6px);
  }

  @media (prefers-reduced-motion: reduce) {
    .slot,
    .enter {
      transition: none;
      animation: none;
    }
  }
</style>
