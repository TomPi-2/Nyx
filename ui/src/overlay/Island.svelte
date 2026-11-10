<!--
  La isla (SPEC secciones 11 y 12): la forma de Nyx arriba en el centro del monitor.
  Los paneles van en otra ventana (Panels.svelte), debajo y con un hueco fijo: esta no
  captura la pantalla, así que Nyx sale siempre en capturas y directos.
-->
<script lang="ts">
  import { onMount } from "svelte";
  import { invoke } from "@tauri-apps/api/core";
  import { emitTo, listen } from "@tauri-apps/api/event";
  import { connectCore } from "$lib/core";
  import type { NyxState, ServerMessage } from "$lib/protocol";
  import Indicator from "./shape/Indicator.svelte";
  import { SHAPE_PAD } from "./shape/nyxShape";
  import { NYX_EVENT, PANEL_MOVE_MS, SHAPE_TOP, type NyxPresence } from "./panels/layout";

  const HIDE_AFTER_MS = 400; // deja terminar la animación de salida antes de ocultar la ventana
  const BACKDROP_MS = 500; // cada cuánto se mira el fondo (blanco o gris)
  const SIDE = 20; // margen a los lados del lienzo de la forma

  let status = $state<NyxState>("idle");
  let connected = $state(false);
  let level = $state(0);
  let size = $state(100); // lado de la forma (Ajustes → Apariencia); llega con «welcome»
  let color = $state("blanco"); // color de Nyx (Ajustes → Apariencia)
  let shapeVisible = $state(false);
  let backdrop = $state<number | null>(null);
  const box = $derived(size * SHAPE_PAD); // lienzo de la forma

  // Partida en marcha (SPEC sección 9): con «solo voz» o «desactivado» no se muestra nada
  // sobre el juego. (Con varios monitores, la isla irá al alternativo.)
  let game = $state<{ active: boolean; mode: "off" | "voice" | "normal" }>({
    active: false,
    mode: "voice",
  });
  const hiddenForGame = $derived(game.active && game.mode !== "normal");

  const active = $derived(status !== "idle" && status !== "muted");

  const shown = $derived(connected && !hiddenForGame && active);

  // Sin Nyx, el panel sube a ocupar su sitio (panels/layout.ts). Esta ventana es la única que
  // sabe si la forma está a la vista (incluido el «pensando» mínimo y la animación de salida),
  // así que es la que avisa a la de los paneles: «gone» cuando la forma ha desaparecido del
  // todo y «coming» cuando va a aparecer. Si el panel estaba arriba, la forma espera a que
  // baje para no pisarlo.
  let bubbleOn = false;
  let waitPanel = $state(false);
  let waitTimer: ReturnType<typeof setTimeout> | undefined;
  let wanted = false;

  function tellPanels(presence: NyxPresence) {
    void emitTo("panels", NYX_EVENT, presence);
  }

  $effect(() => {
    const want = shown;
    if (want && !wanted) {
      tellPanels("coming");
      if (bubbleOn && !shapeVisible) {
        waitPanel = true;
        clearTimeout(waitTimer);
        waitTimer = setTimeout(() => (waitPanel = false), PANEL_MOVE_MS);
      }
    }
    wanted = want;
  });

  function onShapeVisible(visible: boolean) {
    shapeVisible = visible;
    if (!visible) tellPanels("gone");
  }

  // La ventana mide lo que el lienzo de la forma.
  $effect(() => {
    void invoke("island_set_size", { width: box + 2 * SIDE, height: SHAPE_TOP + box, top: 0 });
  });

  // Blanco siempre; gris solo si alrededor hay un fondo muy claro (se mira un anillo
  // alrededor, no debajo: decisión 2026-11-10).
  $effect(() => {
    if (!shown) return;
    const read = async () => {
      const luma = await invoke<number | null>("island_backdrop_luma", {
        cx: window.innerWidth / 2,
        cy: SHAPE_TOP + box / 2,
        radius: size * 0.85,
      });
      if (luma !== null) backdrop = luma;
    };
    void read();
    const timer = setInterval(() => void read(), BACKDROP_MS);
    return () => clearInterval(timer);
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

  function handle(msg: ServerMessage) {
    switch (msg.type) {
      case "state":
        status = msg.state;
        break;
      case "bubble":
        bubbleOn = true;
        break;
      case "bubble_hide":
        bubbleOn = false;
        break;
      case "level":
        level = msg.rms;
        break;
      case "welcome":
        size = msg.indicator_size ?? 100;
        color = msg.nyx_color ?? "blanco";
        break;
      case "settings":
        // Cambiado en Ajustes → Apariencia: se ve al momento.
        size = msg.data.appearance.indicator_size;
        color = msg.data.appearance.nyx_color;
        break;
      case "open_settings":
        // «Abre tus ajustes»: solo esta ventana lo hace (todas reciben el mensaje).
        void invoke("settings_open", { section: msg.section });
        break;
      case "game":
        game = { active: msg.active, mode: msg.mode };
        break;
    }
  }

  onMount(() => {
    const connection = connectCore(handle, (ok) => {
      connected = ok;
      if (!ok) status = "idle";
    });
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

<div class="shape-slot" style:top="{SHAPE_TOP}px">
  <Indicator
    status={hiddenForGame || waitPanel ? "idle" : status}
    {level}
    {size}
    {backdrop}
    {color}
    onvisible={onShapeVisible}
  />
</div>

<style>
  .shape-slot {
    position: absolute;
    left: 50%;
    translate: -50% 0;
  }
</style>
