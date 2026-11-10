<!--
  La isla (SPEC secciones 11 y 12): arriba en el centro del monitor, la forma de Nyx
  (cuadrado líquido-sólido, shape/) y, debajo, la burbuja de respuesta. Las burbujas son las
  provisionales: los paneles se rediseñan desde cero después de la forma.
-->
<script lang="ts">
  import { onMount } from "svelte";
  import { Spring } from "svelte/motion";
  import { invoke } from "@tauri-apps/api/core";
  import { listen } from "@tauri-apps/api/event";
  import { sendNotification } from "@tauri-apps/plugin-notification";
  import { connectCore, type CoreConnection } from "$lib/core";
  import type { ActionButton, NyxState, ServerMessage } from "$lib/protocol";
  import Indicator from "./shape/Indicator.svelte";
  import { SHAPE_PAD } from "./shape/nyxShape";

  const TOP = 12; // margen superior en px
  const MAX_WIDTH = 520;
  const BUBBLE_SPACE = 210; // alto reservado para la burbuja bajo la forma
  const HIDE_AFTER_MS = 400; // deja terminar la animación de salida antes de ocultar la ventana
  const BACKDROP_MS = 500; // cada cuánto se mira el fondo (blanco o gris)

  let status = $state<NyxState>("idle");
  let connected = $state(false);
  let bubble = $state<{
    display: string;
    secondary: string | null;
    actions: ActionButton[];
  } | null>(null);
  let core: CoreConnection | undefined;
  let measuredW = $state(0);
  let measuredH = $state(0);

  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)");
  const springOpts = { stiffness: 0.12, damping: 0.62 };
  const width = new Spring(44, springOpts);
  const height = new Spring(44, springOpts);
  let level = $state(0);
  let size = $state(100); // lado de la forma (Ajustes → Apariencia); llega con «welcome»
  let shapeVisible = $state(false);
  let backdrop = $state<number | null>(null);
  const box = $derived(size * SHAPE_PAD); // lienzo de la forma

  // Partida en marcha (SPEC sección 9): con «solo voz» o «desactivado» no se muestra nada
  // sobre el juego. (Fase 5b: con varios monitores, la isla irá al alternativo.)
  let game = $state<{ active: boolean; mode: "off" | "voice" | "normal" }>({
    active: false,
    mode: "voice",
  });
  const hiddenForGame = $derived(game.active && game.mode !== "normal");

  const active = $derived(status !== "idle" && status !== "muted");
  const shown = $derived(connected && !hiddenForGame && (active || bubble !== null));
  // Mientras la forma está, la burbuja va debajo; si no, arriba del todo.
  const bubbleTop = $derived(active || shapeVisible ? TOP + (box + size) / 2 + 10 : TOP);

  /** Tamaño de la burbuja (provisional hasta el rediseño de los paneles). */
  const target = $derived.by(() => {
    if (bubble) return { w: Math.min(MAX_WIDTH, measuredW), h: measuredH };
    return { w: 0, h: 0 };
  });

  // La ventana se ajusta al tamaño de la forma.
  $effect(() => {
    void invoke("island_set_size", {
      width: Math.max(600, box + 40),
      height: TOP + box + BUBBLE_SPACE,
    });
  });

  // Blanco siempre; gris solo si alrededor hay un fondo muy claro (se mira un anillo
  // alrededor, no debajo: decisión 2026-11-10).
  $effect(() => {
    if (!shown) return;
    const read = async () => {
      const luma = await invoke<number | null>("island_backdrop_luma", {
        cx: window.innerWidth / 2,
        cy: TOP + box / 2,
        radius: size * 0.85,
      });
      if (luma !== null) backdrop = luma;
    };
    void read();
    const timer = setInterval(() => void read(), BACKDROP_MS);
    return () => clearInterval(timer);
  });

  $effect(() => {
    const instant = reduceMotion.matches;
    void width.set(target.w, { instant });
    void height.set(target.h, { instant });
  });

  // Mostrar la ventana al salir de reposo y ocultarla del todo al volver.
  let hideTimer: ReturnType<typeof setTimeout> | undefined;
  $effect(() => {
    clearTimeout(hideTimer);
    if (shown || shapeVisible) {
      void invoke("island_set_visible", { visible: true });
    } else {
      hideTimer = setTimeout(
        () => void invoke("island_set_visible", { visible: false }),
        HIDE_AFTER_MS,
      );
    }
  });

  // Atraviesa los clics salvo con el ratón encima de un botón (SPEC sección 11). Mientras
  // los deja pasar, la página no ve el ratón: Rust lo mira y aquí solo se le dice dónde
  // están los botones (píxeles CSS de la ventana).
  let actionsEl: HTMLDivElement | undefined = $state();
  $effect(() => {
    void width.current; // se recalcula mientras la isla se anima
    void height.current;
    const buttons = shown && actionsEl ? [...actionsEl.querySelectorAll("button")] : [];
    const rects = buttons.map((b) => {
      const r = b.getBoundingClientRect();
      return [r.x, r.y, r.width, r.height];
    });
    void invoke("island_set_hit_rects", { rects });
  });

  function choose(id: string) {
    core?.send({ type: "action", id });
    if (bubble) bubble = { ...bubble, actions: [] }; // evita el doble clic
  }

  function handle(msg: ServerMessage) {
    switch (msg.type) {
      case "state":
        status = msg.state;
        break;
      case "level":
        level = msg.rms;
        break;
      case "welcome":
        size = msg.indicator_size ?? 100;
        break;
      case "bubble":
        bubble = { display: msg.display, secondary: msg.secondary, actions: msg.actions };
        if (msg.alert) {
          // Alarmas: también en el centro de notificaciones, por si no se mira la pantalla.
          sendNotification({ title: msg.display, body: msg.secondary ?? "" });
        }
        break;
      case "bubble_hide":
        bubble = null;
        break;
      case "game":
        game = { active: msg.active, mode: msg.mode };
        break;
    }
  }

  onMount(() => {
    const connection = connectCore(handle, (ok) => {
      connected = ok;
      if (!ok) {
        status = "idle";
        bubble = null;
      }
    });
    core = connection;
    // Atajo de hablar (Win+Alt+H): llega del proceso principal y se reenvía al núcleo.
    const offTalk = listen<boolean>("hotkey://talk", (event) => {
      connection.send({ type: "talk", pressed: event.payload });
    });
    return () => {
      connection.close();
      void offTalk.then((off) => off());
    };
  });
</script>

<!-- Medidor invisible: tamaño natural del contenido de la burbuja. -->
{#if bubble}
  <div class="bubble-content measure" bind:clientWidth={measuredW} bind:clientHeight={measuredH}>
    <span class="display">{bubble.display}</span>
    {#if bubble.secondary}<span class="secondary">{bubble.secondary}</span>{/if}
    {#if bubble.actions.length}
      <div class="actions">
        {#each bubble.actions as action (action.id)}
          <button class:primary={action.primary} tabindex="-1">{action.label}</button>
        {/each}
      </div>
    {/if}
  </div>
{/if}

<div class="shape-slot" style:top="{TOP}px">
  <Indicator
    status={hiddenForGame ? "idle" : status}
    {level}
    {size}
    {backdrop}
    onvisible={(v) => (shapeVisible = v)}
  />
</div>

<div
  class="island"
  class:shown={shown && bubble !== null}
  style:top="{bubbleTop}px"
  style:width="{width.current}px"
  style:height="{height.current}px"
>
  {#if bubble}
    <div class="bubble-content">
      <span class="display">{bubble.display}</span>
      {#if bubble.secondary}<span class="secondary">{bubble.secondary}</span>{/if}
      {#if bubble.actions.length}
        <div class="actions" bind:this={actionsEl}>
          {#each bubble.actions as action (action.id)}
            <button class:primary={action.primary} onclick={() => choose(action.id)}>
              {action.label}
            </button>
          {/each}
        </div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .shape-slot {
    position: absolute;
    left: 50%;
    translate: -50% 0;
  }

  .island {
    position: absolute;
    left: 50%;
    translate: -50% 0;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    border-radius: 22px;
    background: var(--glass-sheen), var(--glass-fallback);
    box-shadow: var(--shadow);
    opacity: 0;
    scale: 0.96;
    filter: blur(6px);
    transition:
      opacity 220ms ease,
      scale 320ms cubic-bezier(0.34, 1.4, 0.64, 1),
      filter 260ms ease;
  }

  .island.shown {
    opacity: 1;
    scale: 1;
    filter: blur(0);
  }

  .bubble-content {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    padding: 14px 26px;
    max-width: 520px;
    white-space: nowrap;
    box-sizing: border-box;
  }

  /* Botones en pastilla, sin bordes (SPEC sección 12): el principal en control-active. */
  .actions {
    display: flex;
    gap: 8px;
    margin-top: 10px;
  }

  button {
    border: none;
    outline: none;
    border-radius: 9999px;
    padding: 7px 18px;
    font: inherit;
    font-size: 13px;
    font-weight: 600;
    color: var(--text);
    background: var(--control);
    cursor: pointer;
    transition:
      filter 120ms ease,
      scale 120ms ease;
  }

  button.primary {
    color: var(--text-on-active);
    background: var(--control-active);
  }

  button:hover {
    filter: brightness(1.12);
  }

  button:active {
    scale: 0.96;
  }

  .measure {
    position: absolute;
    visibility: hidden;
    pointer-events: none;
  }

  .display {
    font-family: "Segoe UI Variable Display", "Segoe UI", system-ui, sans-serif;
    font-size: 28px;
    font-weight: 600;
    color: var(--text);
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
  }

  /* En las respuestas escritas (sin voz) lleva la respuesta entera: puede ocupar varias líneas. */
  .secondary {
    max-width: 100%;
    font-size: 13px;
    line-height: 1.35;
    color: var(--text-secondary);
    text-align: center;
    white-space: normal;
  }

  @media (prefers-reduced-motion: reduce) {
    .island {
      transition: none;
      animation: none;
    }
  }
</style>
