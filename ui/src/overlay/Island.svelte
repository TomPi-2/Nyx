<!--
  La isla (SPEC secciones 11 y 12): la forma de Nyx arriba en el centro del monitor.
  Los paneles van en otra ventana (Panels.svelte), debajo y con un hueco fijo: esta no
  captura la pantalla, así que Nyx sale siempre en capturas y directos.
-->
<script lang="ts">
  import { onMount } from "svelte";
  import { invoke } from "@tauri-apps/api/core";
  import { emitTo, listen } from "@tauri-apps/api/event";
  import { getCurrentWebviewWindow } from "@tauri-apps/api/webviewWindow";
  import { connectCore, type CoreConnection } from "$lib/core";
  import { MOVE_EVENT, MOVE_IN_MS, type MovePhase } from "$lib/motion";
  import type {
    GlassInfo,
    MonitorSettings,
    NyxState,
    ReadyIndicator,
    ServerMessage,
  } from "$lib/protocol";
  import Indicator from "./shape/Indicator.svelte";
  import { SHAPE_PAD } from "./shape/nyxShape";
  import {
    INPUT_EVENT,
    NYX_EVENT,
    PANEL_MOVE_MS,
    READY_TEST_EVENT,
    SHAPE_TOP,
    type InputLayout,
    type NyxPresence,
  } from "./panels/layout";

  const HIDE_AFTER_MS = 400; // deja terminar la animación de salida antes de ocultar la ventana
  const BACKDROP_MS = 500; // cada cuánto se mira el fondo (blanco o gris)
  const SIDE = 20; // margen a los lados del lienzo de la forma

  let status = $state<NyxState>("idle");
  let connected = $state(false);
  let level = $state(0);
  let size = $state(100); // lado de la forma (Ajustes → Apariencia); llega con «welcome»
  let color = $state("blanco"); // color de Nyx (Ajustes → Apariencia)
  let welcomeAsked = false;
  let shapeVisible = $state(false);
  let backdrop = $state<number | null>(null);
  const box = $derived(size * SHAPE_PAD); // lienzo de la forma

  // Partida en marcha (SPEC sección 9). Con «desactivado» no se muestra nada; con «solo voz»,
  // el coordinador de monitores (monitors.rs) la lleva a otro monitor o, si no hay otro, no
  // la muestra en ninguno.
  let game = $state<{ active: boolean; mode: "off" | "voice" | "normal"; monitor: string }>({
    active: false,
    mode: "voice",
    monitor: "",
  });
  const hiddenForGame = $derived(game.active && game.mode === "off");

  // En qué monitor aparece (Ajustes → Apariencia y Modo partida): se le dice al coordinador,
  // que mueve juntas la forma y los paneles.
  let monitor = $state<MonitorSettings | null>(null);
  let altMonitor = $state<string | null>(null);
  $effect(() => {
    const policy = {
      follow: monitor?.follow ?? "cursor",
      fixed: monitor?.fixed ?? null,
      transition: monitor?.transition ?? true,
      alt: altMonitor,
      game: game.active ? { mode: game.mode, monitor: game.monitor } : null,
    };
    void invoke("overlay_policy", { policy });
  });

  // Cambio de monitor estando visible: se encoge aquí y aparece allí (island.rs).
  let moving = $state<MovePhase | null>(null);
  let movingTimer: ReturnType<typeof setTimeout> | undefined;

  const active = $derived(status !== "idle" && status !== "muted");

  // Primer arranque guiado (9.10): Nyx se queda a la vista todo el rato, aunque no hable.
  let setupOn = $state(false);
  let setupLinger = $state(false);
  let setupTimer: ReturnType<typeof setTimeout> | undefined;
  $effect(() => {
    clearTimeout(setupTimer);
    if (setupLinger && status !== "speaking") {
      setupTimer = setTimeout(() => (setupLinger = false), 2500);
    }
  });

  // «Nyx lista» (9.04): la onda que sale de su sitio y cruza los monitores o, si no se puede
  // (partida, «reducir movimiento», cristal en Bajo o para salir en capturas), Nyx aparece y
  // desaparece. Lo elegido en Ajustes → Apariencia → «Al estar lista».
  const GREET_MS = 1800;
  let readyIndicator: ReadyIndicator = "onda";
  let glassInfo: GlassInfo | null = null;
  let greeting = $state(false);
  let greetTimer: ReturnType<typeof setTimeout> | undefined;

  function ready() {
    if (readyIndicator === "nada" || hiddenForGame) return;
    const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const lowGlass = glassInfo?.quality === "bajo" || glassInfo?.show_in_captures === true;
    if (readyIndicator === "onda" && !game.active && !calm && !lowGlass) {
      // Del centro de su forma, aunque ahora esté oculta (wave.rs).
      void invoke("wave_play", { cy: SHAPE_TOP + box / 2 }).catch(greet);
      return;
    }
    greet();
  }

  function greet() {
    greeting = true;
    clearTimeout(greetTimer);
    greetTimer = setTimeout(() => (greeting = false), GREET_MS);
  }

  const shown = $derived(
    connected && !hiddenForGame && (active || setupOn || setupLinger || greeting),
  );

  // Sin Nyx, el panel sube a ocupar su sitio (panels/layout.ts). Esta ventana es la única que
  // sabe si la forma está a la vista (incluido el «pensando» mínimo y la animación de salida),
  // así que es la que avisa a la de los paneles: «gone» cuando la forma ha desaparecido del
  // todo y «coming» cuando va a aparecer. Si el panel estaba arriba, la forma espera a que
  // baje para no pisarlo.
  let bubbleOn = false;
  /** El campo de texto está abierto (en el sitio de Nyx si no está): también hay que esperar. */
  let inputOpen = false;
  let waitPanel = $state(false);
  // En reposo la forma se va; en el primer arranque se queda esperando (como al confirmar).
  const shapeStatus = $derived<NyxState>(
    hiddenForGame || waitPanel
      ? "idle"
      : status === "idle" && (setupOn || setupLinger || greeting)
        ? "confirm"
        : status,
  );
  let waitTimer: ReturnType<typeof setTimeout> | undefined;
  let wanted = false;

  function tellPanels(presence: NyxPresence) {
    void emitTo("panels", NYX_EVENT, presence);
    void emitTo("input", NYX_EVENT, presence);
  }

  $effect(() => {
    const want = shown;
    if (want && !wanted) {
      tellPanels("coming");
      if ((bubbleOn || inputOpen) && !shapeVisible) {
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
        readyIndicator = msg.ready_indicator ?? "onda";
        glassInfo = msg.glass ?? null;
        // Primera vez: el primer arranque guiado por Nyx (9.10; una vez por sesión; si se
        // cierra sin terminar, vuelve a salir la próxima vez que se abra Nyx).
        if (msg.onboarding_done === false && !welcomeAsked) {
          welcomeAsked = true;
          core?.send({ type: "setup_flow", action: "start" });
        }
        break;
      case "setup_flow_state":
        if (setupOn && !msg.state.active && msg.state.mode === "first_run") setupLinger = true;
        setupOn = msg.state.active;
        break;
      case "settings":
        // Cambiado en Ajustes → Apariencia: se ve al momento.
        size = msg.data.appearance.indicator_size;
        color = msg.data.appearance.nyx_color;
        readyIndicator = msg.data.appearance.ready_indicator;
        glassInfo = msg.data.appearance.glass;
        break;
      case "nyx_ready":
        ready();
        break;
      case "update_apply":
        // El núcleo ha elegido el momento (9.06): la app lo para y Velopack cambia de versión.
        void invoke("update_apply").catch((err) => console.warn("Actualización:", err));
        break;
      case "open_settings":
        // «Abre tus ajustes»: solo esta ventana lo hace (todas reciben el mensaje).
        void invoke("settings_open", { section: msg.section });
        break;
      case "game":
        game = { active: msg.active, mode: msg.mode, monitor: msg.monitor ?? "" };
        break;
    }
    if (msg.type === "settings") {
      monitor = msg.data.appearance.monitor;
      altMonitor = msg.data.game.alt_monitor;
      // Canal de actualizaciones (Ajustes → General): la app empieza a mirar al saberlo.
      void invoke("update_configure", { channel: msg.data.updates.channel });
    }
  }

  let core: CoreConnection | undefined;

  onMount(() => {
    const connection = connectCore(handle, (ok) => {
      connected = ok;
      if (!ok) {
        status = "idle";
        // Reinicio del núcleo en mitad del primer arranque: se olvida y, si no estaba
        // terminado, se vuelve a pedir al conectar (antes se quedaba colgado).
        setupOn = false;
        setupLinger = false;
        welcomeAsked = false;
      }
      // Los ajustes de monitor no van en «welcome»: se piden (la respuesta llega a todas).
      if (ok) connection.send({ type: "settings_get" });
    });
    core = connection;
    const offMove = getCurrentWebviewWindow().listen<MovePhase>(MOVE_EVENT, (e) => {
      clearTimeout(movingTimer);
      moving = e.payload;
      if (e.payload === "in") movingTimer = setTimeout(() => (moving = null), MOVE_IN_MS);
    });
    const offInput = getCurrentWebviewWindow().listen<InputLayout>(INPUT_EVENT, (e) => {
      inputOpen = e.payload.open;
    });
    const offReady = getCurrentWebviewWindow().listen(READY_TEST_EVENT, () => ready());
    // Versión nueva descargada (updater.rs): el núcleo decide cuándo aplicarla.
    const offUpdate = getCurrentWebviewWindow().listen<{ version: string }>("update://ready", (e) =>
      connection.send({ type: "update", action: "ready", version: e.payload.version }),
    );
    // Atajo de hablar (Win+Alt+H): llega del proceso principal y se reenvía al núcleo.
    const offTalk = listen<boolean>("hotkey://talk", (event) => {
      connection.send({ type: "talk", pressed: event.payload });
    });
    return () => {
      connection.close();
      void offTalk.then((off) => off());
      void offMove.then((off) => off());
      void offInput.then((off) => off());
      void offReady.then((off) => off());
      void offUpdate.then((off) => off());
    };
  });
</script>

<div
  class="shape-slot"
  class:move-out={moving === "out"}
  class:move-in={moving === "in"}
  style:top="{SHAPE_TOP}px"
>
  <Indicator
    status={shapeStatus}
    {level}
    {size}
    {backdrop}
    {color}
    gaming={game.active}
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
