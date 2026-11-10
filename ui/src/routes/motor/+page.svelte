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
  <section class="settings" use:glassShape={{ radius: 28 }} use:glassPoke>
    <header data-tauri-drag-region>
      <div class="titles" data-tauri-drag-region>
        <h1 data-tauri-drag-region>Motor gráfico</h1>
        <p data-tauri-drag-region>Ejemplos del cristal · arrastra desde aquí</p>
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
  </section>

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
      Pasa ventanas, vídeos o fondos por detrás para ver el cristal en tiempo real. Las capturas se
      quedan en la GPU: no se guardan ni salen del equipo.
    </p>
  </aside>
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
