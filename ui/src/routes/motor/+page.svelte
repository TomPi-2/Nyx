<!--
  Galería del motor de cristal (bandeja → «Motor gráfico (ejemplos)»).

  Paneles de muestra sobre el cristal (uno del tamaño de Ajustes, una burbuja, una
  confirmación y la cápsula de «pensando») y controles para probar los niveles, el borde
  líquido y los parámetros viendo el coste en directo. La burbuja sin foco abre una
  segunda ventana como la isla, que es el caso en el que el Acrylic de Windows fallaba.
-->
<script lang="ts">
  import { onMount } from "svelte";
  import { invoke } from "@tauri-apps/api/core";
  import { emitTo } from "@tauri-apps/api/event";
  import {
    DEFAULT_GLASS,
    edgeLevelToPx,
    edgePxToLevel,
    glass,
    glassPoke,
    glassShape,
    type GlassLevel,
    type GlassMotion,
    type GlassOptions,
    type GlassPreference,
    type GlassStats,
  } from "$lib/glass";
  import type { NyxState } from "$lib/protocol";
  import Indicator from "$overlay/shape/Indicator.svelte";
  import AlertPanel from "$overlay/panels/AlertPanel.svelte";
  import ConfirmPanel from "$overlay/panels/ConfirmPanel.svelte";
  import InputPanel from "$overlay/panels/InputPanel.svelte";
  import ResponsePanel from "$overlay/panels/ResponsePanel.svelte";
  import UndoPanel from "$overlay/panels/UndoPanel.svelte";
  import { PANEL_GAP, SHAPE_TOP, panelTop, shapeReach } from "$overlay/panels/layout";

  const QUALITIES: { value: GlassPreference; label: string }[] = [
    { value: "auto", label: "Auto" },
    { value: "alto", label: "Alto" },
    { value: "medio", label: "Medio" },
    { value: "bajo", label: "Bajo" },
  ];
  const LEVEL_LABEL: Record<GlassLevel, string> = { alto: "Alto", medio: "Medio", bajo: "Bajo" };
  const MOTIONS: { value: GlassMotion; label: string }[] = [
    { value: "siempre", label: "Siempre" },
    { value: "interaccion", label: "Al interactuar" },
    { value: "quieto", label: "Quieto" },
  ];
  const QUALITY_HINT: Record<GlassPreference, string> = {
    auto: "Nyx elige el nivel: baja solo con batería, ahorro de energía, transparencias desactivadas o si la GPU no llega",
    alto: "Desenfoque en tiempo real, refracción en el borde y brillo",
    medio: "Desenfoque en tiempo real, tinte y brillo sencillo",
    bajo: "Tinte translúcido: no mira lo de detrás",
  };
  const GAME_NOTE = "En partida se cambia a Bajo automáticamente, sin excepción.";

  type Slider = {
    key: keyof GlassOptions;
    label: string;
    min: number;
    max: number;
    step: number;
    unit?: string;
  };
  const SLIDERS: Slider[] = [
    { key: "speed", label: "Velocidad", min: 0.2, max: 3, step: 0.1, unit: "×" },
    { key: "blur", label: "Desenfoque", min: 0, max: 1, step: 0.05 },
    { key: "tint", label: "Tinte gris", min: 0, max: 0.9, step: 0.05 },
    { key: "refraction", label: "Refracción", min: 0, max: 30, step: 1, unit: "px" },
    { key: "specular", label: "Brillo", min: 0, max: 1, step: 0.05 },
    { key: "saturation", label: "Saturación", min: 0.5, max: 1.8, step: 0.05 },
    { key: "shadow", label: "Sombra", min: 0, max: 1, step: 0.05 },
  ];

  // Pestaña «Paneles»: prototipo de los paneles de la isla con la forma de Nyx encima.
  type Tab = "motor" | "paneles";
  type NyxPreview = "oculta" | "espera" | "escucha" | "piensa" | "habla";
  type PanelKind = "respuesta" | "larga" | "confirmacion" | "deshacer" | "aviso" | "texto" | "nada";
  const NYX_STATES: { value: NyxPreview; label: string }[] = [
    { value: "espera", label: "Espera" },
    { value: "escucha", label: "Escucha" },
    { value: "piensa", label: "Piensa" },
    { value: "habla", label: "Habla" },
    { value: "oculta", label: "Oculta" },
  ];
  const PANEL_KINDS: { value: PanelKind; label: string }[] = [
    { value: "respuesta", label: "Respuesta" },
    { value: "larga", label: "Respuesta larga" },
    { value: "confirmacion", label: "Confirmación" },
    { value: "deshacer", label: "Deshacer" },
    { value: "aviso", label: "Aviso" },
    { value: "texto", label: "Campo de texto" },
    { value: "nada", label: "Ninguno" },
  ];
  const NYX_STATUS: Record<NyxPreview, NyxState> = {
    oculta: "idle",
    espera: "listening",
    escucha: "listening",
    piensa: "thinking",
    habla: "speaking",
  };
  let tab = $state<Tab>("motor");
  let nyxPreview = $state<NyxPreview>("espera");
  let panelKind = $state<PanelKind>("respuesta");
  let nyxSize = $state(100);
  let level = $state(0);
  let typed = $state("");
  // Cambiar de panel lo vuelve a montar (reinicia cuentas atrás).
  let panelRun = $state(0);

  function showPanel(kind: PanelKind) {
    panelKind = kind;
    panelRun++;
  }

  // El panel se desplaza sin cambiar de tamaño: el cristal tiene que saberlo.
  $effect(() => {
    void nyxSize;
    void options.amplitude;
    void tab;
    glass.refresh();
  });

  // Voz simulada para «escucha» y «habla».
  $effect(() => {
    if (tab !== "paneles" || (nyxPreview !== "escucha" && nyxPreview !== "habla")) {
      level = 0;
      return;
    }
    const start = performance.now();
    const timer = setInterval(() => {
      const t = (performance.now() - start) / 1000;
      level = 0.04 + 0.05 * Math.abs(Math.sin(t * 5.3) * Math.sin(t * 2.1 + 1));
    }, 33);
    return () => clearInterval(timer);
  });

  let options = $state<GlassOptions>({ ...glass.current });
  // Amplitud del borde como en Ajustes: de 0 a 10, el 5 son 3,5 px.
  let edge = $state(edgePxToLevel(glass.current.amplitude));
  let stats = $state<GlassStats | null>(null);
  let game = $state(false);
  let bubble = $state(false);

  const fmt = (n: number, digits = 1) =>
    n.toLocaleString("es-ES", { maximumFractionDigits: digits, minimumFractionDigits: 0 });

  function send() {
    const snapshot = $state.snapshot(options);
    glass.set(snapshot);
    if (bubble) void emitTo("glass-bubble", "glass-gallery-options", snapshot);
  }

  function pick<K extends keyof GlassOptions>(key: K, value: GlassOptions[K]) {
    options[key] = value;
    send();
  }

  function setEdge() {
    options.amplitude = edgeLevelToPx(edge);
    send();
  }

  function reset() {
    options = { ...DEFAULT_GLASS, dark: options.dark };
    edge = edgePxToLevel(options.amplitude);
    send();
  }

  function toggleGame() {
    game = !game;
    glass.setGame(game);
  }

  async function toggleBubble() {
    bubble = await invoke<boolean>("glass_toggle_bubble");
    // La burbuja tarda un momento en cargar: se le mandan las opciones al estar lista.
    if (bubble) setTimeout(send, 600);
  }

  function close() {
    glass.detach();
    void invoke("glass_close_gallery");
  }

  onMount(() => {
    void glass.attach($state.snapshot(options));
    const unlisten = glass.onStats((s) => (stats = s));
    return () => {
      void unlisten.then((f) => f());
      glass.detach();
    };
  });

  const reduced = $derived(stats?.reason != null);
</script>

<main>
  <section
    class="settings"
    class:narrow={tab === "paneles"}
    use:glassShape={{ radius: 28 }}
    use:glassPoke
  >
    <header data-tauri-drag-region>
      <div class="titles" data-tauri-drag-region>
        <h1 data-tauri-drag-region>Motor gráfico</h1>
        <p data-tauri-drag-region>Ejemplos del cristal · arrastra desde aquí</p>
      </div>
      <div class="segmented tabs">
        <button class:on={tab === "motor"} onclick={() => (tab = "motor")}>Motor</button>
        <button class:on={tab === "paneles"} onclick={() => (tab = "paneles")}>Paneles</button>
      </div>
      <button class="round" onclick={close} aria-label="Cerrar">
        <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
          <path
            d="M4 4l8 8M12 4l-8 8"
            stroke="currentColor"
            stroke-width="1.6"
            stroke-linecap="round"
          />
        </svg>
      </button>
    </header>

    {#if tab === "paneles"}
      <div class="group">
        <span class="label wide">Nyx</span>
        <div class="segmented">
          {#each NYX_STATES as n (n.value)}
            <button class:on={nyxPreview === n.value} onclick={() => (nyxPreview = n.value)}>
              {n.label}
            </button>
          {/each}
        </div>
      </div>

      <div class="group">
        <span class="label wide">Panel</span>
        <div class="chips">
          {#each PANEL_KINDS as p (p.value)}
            <button class:on={panelKind === p.value} onclick={() => showPanel(p.value)}>
              {p.label}
            </button>
          {/each}
        </div>
      </div>

      <div class="group">
        <span class="label wide">Nivel</span>
        <div class="segmented">
          {#each QUALITIES as q (q.value)}
            <button class:on={options.quality === q.value} onclick={() => pick("quality", q.value)}>
              {q.label}
            </button>
          {/each}
        </div>
      </div>

      <div class="sliders single">
        <label class="slider">
          <span class="slider-head">
            <span>Amplitud del borde</span>
            <span class="secondary">{fmt(edge, 0)} · {fmt(options.amplitude, 1)} px</span>
          </span>
          <input
            type="range"
            min="0"
            max="10"
            step="1"
            bind:value={edge}
            oninput={setEdge}
            style="--p: {edge * 10}%"
          />
        </label>
        <label class="slider">
          <span class="slider-head">
            <span>Tamaño de Nyx</span>
            <span class="secondary">{nyxSize} px</span>
          </span>
          <input
            type="range"
            min="60"
            max="160"
            step="10"
            bind:value={nyxSize}
            style="--p: {((nyxSize - 60) / 100) * 100}%"
          />
        </label>
      </div>

      <p class="note-card">
        El panel empieza {PANEL_GAP} px por debajo de lo más lejos que puede llegar Nyx (su lienzo:
        {fmt(shapeReach(nyxSize), 0)} px) más la ondulación de su borde ({fmt(options.amplitude, 1)} px).
        Así no se tocan ni al girar, dividirse en cuatro o estirarse al hablar.
      </p>
    {:else}
      <div class="card stats">
        {#if stats?.failed}
          <strong>El motor no puede dibujar aquí</strong>
          <span class="secondary">{stats.failed} · se usa el tinte de CSS</span>
        {:else if stats}
          <strong>
            {stats.requested === "auto" ? "Auto · " : ""}{LEVEL_LABEL[stats.effective]}
            {#if reduced}<span class="secondary">({stats.reason})</span>{/if}
          </strong>
          <span class="secondary">
            {fmt(stats.fps, 0)} fps
            {#if stats.gpuMs !== null}
              · GPU {fmt(stats.gpuMs, 2)} ms por fotograma
            {/if}
            {#if stats.gpuLoad !== null}
              · carga ≈ {fmt(stats.gpuLoad, 1)} %
            {/if}
            {#if stats.captureFps !== null}
              · capturas {fmt(stats.captureFps, 0)}/s
            {/if}
          </span>
          <span class="tertiary">{stats.adapter}</span>
        {:else}
          <span class="secondary">Arrancando el motor…</span>
        {/if}
      </div>

      <div class="row">
        <span class="label">Nivel</span>
        <div class="segmented">
          {#each QUALITIES as q (q.value)}
            <button class:on={options.quality === q.value} onclick={() => pick("quality", q.value)}>
              {q.label}
            </button>
          {/each}
        </div>
      </div>
      <p class="hint">
        {QUALITY_HINT[options.quality]}{#if options.quality !== "auto"}. {GAME_NOTE}{/if}
      </p>

      <div class="row">
        <span class="label">Borde</span>
        <div class="segmented">
          {#each MOTIONS as m (m.value)}
            <button class:on={options.motion === m.value} onclick={() => pick("motion", m.value)}>
              {m.label}
            </button>
          {/each}
        </div>
      </div>

      <div class="sliders">
        <label class="slider">
          <span class="slider-head">
            <span>Amplitud del borde</span>
            <span class="secondary">{fmt(edge, 0)} · {fmt(options.amplitude, 1)} px</span>
          </span>
          <input
            type="range"
            min="0"
            max="10"
            step="1"
            bind:value={edge}
            oninput={setEdge}
            style="--p: {edge * 10}%"
          />
        </label>
        {#each SLIDERS as s (s.key)}
          <label class="slider">
            <span class="slider-head">
              <span>{s.label}</span>
              <span class="secondary">{fmt(options[s.key] as number, 2)}{s.unit ?? ""}</span>
            </span>
            <input
              type="range"
              min={s.min}
              max={s.max}
              step={s.step}
              bind:value={options[s.key] as number}
              oninput={send}
              style="--p: {(((options[s.key] as number) - s.min) / (s.max - s.min)) * 100}%"
            />
          </label>
        {/each}
      </div>

      <div class="toggles">
        <button class="toggle" class:on={game} onclick={toggleGame}>
          <span class="knob"></span>Simular partida
        </button>
      </div>

      <footer>
        <button class="pill" class:primary={bubble} onclick={toggleBubble}>
          {bubble ? "Cerrar la burbuja sin foco" : "Abrir una burbuja sin foco"}
        </button>
        <button class="pill" onclick={reset}>Restablecer</button>
      </footer>
    {/if}
  </section>

  {#if tab === "paneles"}
    <div class="island">
      <div class="nyx" style:top="{SHAPE_TOP}px">
        <Indicator status={NYX_STATUS[nyxPreview]} {level} size={nyxSize} backdrop={null} />
      </div>
      <div class="panel-slot" style:top="{panelTop(nyxSize, options.amplitude)}px">
        {#key panelRun}
          {#if panelKind === "respuesta"}
            <ResponsePanel display="22 °C" secondary="Madrid · soleado, máxima de 25 °C" />
          {:else if panelKind === "larga"}
            <ResponsePanel
              display="La fotosíntesis es el proceso por el que las plantas convierten la luz del sol, el agua y el dióxido de carbono en glucosa y oxígeno."
              secondary="Respuesta del modelo local"
            />
          {:else if panelKind === "confirmacion"}
            <ConfirmPanel
              title="¿Muevo 12 archivos de Fondos a la papelera?"
              detail="Se pueden recuperar desde la papelera de Windows."
              confirmLabel="Mover a la papelera"
            />
          {:else if panelKind === "deshacer"}
            <UndoPanel text="«Informe.docx» movido a Documentos" secondary="Hace un momento" />
          {:else if panelKind === "aviso"}
            <AlertPanel title="Alarma · 8:00" secondary="Sacar al perro" />
          {:else if panelKind === "texto"}
            <InputPanel bind:value={typed} />
          {/if}
        {/key}
      </div>
    </div>
  {:else}
    <aside>
      <div class="bubble" use:glassShape={{ radius: 26 }} use:glassPoke>
        <span class="display">Alarma puesta</span>
        <span class="secondary">mañana a las 8:00</span>
      </div>

      <div class="confirm" use:glassShape={{ radius: 26 }} use:glassPoke>
        <span class="title">¿Muevo «Notas viejas» a la papelera?</span>
        <span class="secondary">Se puede deshacer durante 10 segundos</span>
        <div class="actions">
          <button class="pill primary">Sí</button>
          <button class="pill">No</button>
        </div>
      </div>

      <div class="small">
        <div class="capsule" use:glassShape={{ radius: 22, wobble: 0.6 }}>
          <span class="dots"><i></i><i></i><i></i></span>
        </div>
        <div class="dot" use:glassShape={{ radius: 22, wobble: 0.6 }}></div>
      </div>

      <p class="note">
        Pasa ventanas, vídeos o fondos por detrás para ver el cristal en tiempo real. Las capturas
        se quedan en la GPU: no se guardan ni salen del equipo.
      </p>
    </aside>
  {/if}
</main>

<style>
  main {
    display: flex;
    gap: 36px;
    padding: 36px 40px 40px;
    height: 100%;
  }

  .settings {
    display: flex;
    flex-direction: column;
    gap: 14px;
    width: 580px;
    padding: 22px 24px 22px;
    border-radius: 28px;
  }

  .settings.narrow {
    flex: none;
    width: 400px;
  }

  header {
    gap: 12px;
  }

  .titles {
    flex: 1;
    min-width: 0;
  }

  .segmented.tabs {
    flex: none;
  }

  .tabs button {
    padding: 6px 14px;
  }

  .group {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .label.wide {
    width: auto;
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .chips button {
    padding: 7px 14px;
    border-radius: 999px;
    background: var(--control);
    font-size: 13px;
    transition:
      background 160ms ease,
      color 160ms ease;
  }

  .chips button.on {
    background: var(--control-active);
    color: var(--text-on-active);
  }

  .sliders.single {
    grid-template-columns: 1fr;
  }

  .note-card {
    margin: auto 0 0;
    padding: 12px 16px;
    border-radius: 18px;
    background: var(--glass-raised);
    font-size: 12px;
    line-height: 1.5;
    color: var(--text-secondary);
  }

  /* Vista previa de la isla: la forma arriba y el panel debajo, con el hueco fijo. */
  .island {
    position: relative;
    flex: 1;
    min-width: 0;
  }

  .nyx {
    position: absolute;
    left: 50%;
    transform: translateX(-50%);
  }

  .panel-slot {
    position: absolute;
    left: 0;
    right: 0;
    display: flex;
    justify-content: center;
  }

  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  h1 {
    margin: 0;
    font-family: "Segoe UI Variable Display", "Segoe UI", system-ui, sans-serif;
    font-size: 22px;
    font-weight: 600;
  }

  header p {
    margin: 2px 0 0;
    font-size: 12px;
    color: var(--text-secondary);
  }

  .card {
    display: flex;
    flex-direction: column;
    gap: 3px;
    padding: 12px 16px;
    border-radius: 18px;
    background: var(--glass-raised);
    font-size: 13px;
  }

  .stats strong {
    font-weight: 600;
  }

  .secondary {
    color: var(--text-secondary);
    font-weight: 400;
  }

  .tertiary {
    color: var(--text-tertiary);
    font-size: 12px;
  }

  .row {
    display: flex;
    align-items: center;
    gap: 14px;
  }

  .label {
    width: 52px;
    font-size: 13px;
    color: var(--text-secondary);
  }

  .hint {
    margin: -6px 0 0 66px;
    font-size: 12px;
    color: var(--text-tertiary);
  }

  button {
    font: inherit;
    color: inherit;
    border: none;
    cursor: pointer;
  }

  .segmented {
    display: flex;
    flex: 1;
    gap: 4px;
    padding: 4px;
    border-radius: 999px;
    background: var(--control);
  }

  .segmented button {
    flex: 1;
    padding: 7px 10px;
    border-radius: 999px;
    background: transparent;
    font-size: 13px;
    transition:
      background 160ms ease,
      color 160ms ease;
  }

  .segmented button.on {
    background: var(--control-active);
    color: var(--text-on-active);
  }

  .sliders {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px 22px;
    margin-top: 2px;
  }

  .slider {
    display: flex;
    flex-direction: column;
    gap: 6px;
    font-size: 13px;
  }

  .slider-head {
    display: flex;
    justify-content: space-between;
  }

  input[type="range"] {
    appearance: none;
    width: 100%;
    height: 6px;
    margin: 4px 0;
    border-radius: 999px;
    background: linear-gradient(
      90deg,
      var(--control-active) 0 var(--p),
      var(--control) var(--p) 100%
    );
    outline: none;
  }

  input[type="range"]::-webkit-slider-thumb {
    appearance: none;
    width: 18px;
    height: 18px;
    border-radius: 50%;
    background: var(--text);
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
  }

  .toggles {
    display: flex;
    gap: 22px;
    margin-top: 4px;
  }

  .toggle {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 0;
    background: none;
    font-size: 13px;
  }

  .knob {
    position: relative;
    width: 38px;
    height: 22px;
    border-radius: 999px;
    background: var(--control);
    transition: background 160ms ease;
  }

  .knob::after {
    content: "";
    position: absolute;
    top: 3px;
    left: 3px;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--text);
    transition: transform 160ms ease;
  }

  .toggle.on .knob {
    background: var(--control-active);
  }

  .toggle.on .knob::after {
    transform: translateX(16px);
    background: var(--text-on-active);
  }

  footer {
    display: flex;
    gap: 10px;
    margin-top: auto;
  }

  .pill {
    padding: 9px 18px;
    border-radius: 999px;
    background: var(--control);
    font-size: 13px;
  }

  .pill.primary {
    background: var(--control-active);
    color: var(--text-on-active);
  }

  .round {
    display: grid;
    place-items: center;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: var(--control);
  }

  aside {
    display: flex;
    flex-direction: column;
    gap: 28px;
    width: 340px;
    padding-top: 8px;
  }

  .bubble {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 96px;
    border-radius: 26px;
  }

  .display {
    font-family: "Segoe UI Variable Display", "Segoe UI", system-ui, sans-serif;
    font-size: 26px;
    font-weight: 600;
  }

  .bubble .secondary,
  .confirm .secondary {
    font-size: 13px;
  }

  .confirm {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 20px 22px;
    border-radius: 26px;
  }

  .confirm .title {
    font-size: 15px;
    font-weight: 600;
  }

  .actions {
    display: flex;
    gap: 8px;
    margin-top: 10px;
  }

  .actions .pill {
    flex: 1;
  }

  .small {
    display: flex;
    gap: 16px;
    align-items: center;
  }

  .capsule {
    display: grid;
    place-items: center;
    width: 120px;
    height: 44px;
    border-radius: 22px;
  }

  .dots {
    display: flex;
    gap: 6px;
  }

  .dots i {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--text-secondary);
    animation: pulse 1.2s ease-in-out infinite;
  }

  .dots i:nth-child(2) {
    animation-delay: 0.15s;
  }

  .dots i:nth-child(3) {
    animation-delay: 0.3s;
  }

  @keyframes pulse {
    50% {
      opacity: 0.3;
    }
  }

  .dot {
    width: 44px;
    height: 44px;
    border-radius: 22px;
  }

  .note {
    margin: 0;
    font-size: 12px;
    line-height: 1.5;
    color: var(--text-secondary);
    text-shadow: 0 1px 6px rgba(0, 0, 0, 0.5);
  }
</style>
