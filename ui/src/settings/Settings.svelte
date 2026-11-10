<!--
  Ventana de Ajustes (SPEC sección 13): cristal del motor en toda la ventana, barra de título
  propia (zona de arrastre y tres botones circulares que aparecen al pasar el ratón), barra
  lateral con las secciones en pastilla y, a la derecha, grupos de opciones en tarjetas.
  5c‑1: Apariencia, Respuestas y Modo partida; el resto de secciones llega en 5c‑2.
-->
<script lang="ts">
  import { onMount, type Component } from "svelte";
  import { getCurrentWindow } from "@tauri-apps/api/window";
  import { glass, glassFromSettings, glassPoke, glassShape } from "$lib/glass";
  import Apariencia from "./sections/Apariencia.svelte";
  import ModoPartida from "./sections/ModoPartida.svelte";
  import Respuestas from "./sections/Respuestas.svelte";
  import { settings } from "./store.svelte";

  type SectionId = "apariencia" | "respuestas" | "partida";
  const SECTIONS: { id: SectionId; label: string; component: Component }[] = [
    { id: "apariencia", label: "Apariencia", component: Apariencia },
    { id: "respuestas", label: "Respuestas", component: Respuestas },
    { id: "partida", label: "Modo partida", component: ModoPartida },
  ];
  const RADIUS = 28;

  let current = $state<SectionId>("apariencia");
  let maximized = $state(false);
  const section = $derived(SECTIONS.find((s) => s.id === current)!);
  const win = getCurrentWindow();

  // El cristal de Ajustes sigue los ajustes de Apariencia. Es una ventana que puede estar
  // abierta mucho rato: «Siempre» se queda en «al interactuar» para no redibujar sin parar.
  $effect(() => {
    const info = settings.data?.appearance.glass;
    if (!info) return;
    // Misma regla que los paneles (con «Mostrar Nyx en capturas», Bajo).
    const options = glassFromSettings(info);
    if (options.motion === "siempre") options.motion = "interaccion";
    glass.set(options);
  });

  onMount(() => {
    const disconnect = settings.connect();
    void glass.attach({ motion: "interaccion" });
    const updateMax = async () => {
      maximized = await win.isMaximized();
      glass.refresh();
    };
    void updateMax();
    const offResize = win.onResized(() => void updateMax());
    return () => {
      disconnect();
      glass.detach();
      void offResize.then((off) => off());
    };
  });
</script>

<div
  class="window"
  class:maximized
  use:glassShape={{ radius: maximized ? 0 : RADIUS, wobble: maximized ? 0 : 0.6 }}
  use:glassPoke
>
  <header class="titlebar" data-tauri-drag-region>
    <span class="title" data-tauri-drag-region>Ajustes</span>
    <div class="buttons">
      <button aria-label="Minimizar" onclick={() => void win.minimize()}>
        <svg viewBox="0 0 12 12" width="10" height="10" aria-hidden="true">
          <path d="M2.5 6h7" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
        </svg>
      </button>
      <button
        aria-label={maximized ? "Restaurar" : "Maximizar"}
        onclick={() => void win.toggleMaximize()}
      >
        <svg viewBox="0 0 12 12" width="10" height="10" aria-hidden="true">
          <rect
            x="2.5"
            y="2.5"
            width="7"
            height="7"
            rx="2"
            fill="none"
            stroke="currentColor"
            stroke-width="1.4"
          />
        </svg>
      </button>
      <button aria-label="Cerrar" onclick={() => void win.close()}>
        <svg viewBox="0 0 12 12" width="10" height="10" aria-hidden="true">
          <path
            d="M3 3l6 6M9 3l-6 6"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
          />
        </svg>
      </button>
    </div>
  </header>

  <div class="body">
    <nav aria-label="Secciones">
      {#each SECTIONS as s (s.id)}
        <button class:on={current === s.id} onclick={() => (current = s.id)}>{s.label}</button>
      {/each}
    </nav>

    <main>
      <h2>{section.label}</h2>
      {#if !settings.connected && !settings.data}
        <p class="status">Esperando a Nyx…</p>
      {:else}
        <section.component />
      {/if}
    </main>
  </div>

  {#if settings.error || settings.restart.length}
    <div class="toast" role="status">
      {settings.error ??
        "Algunos cambios se aplican al reiniciar Nyx (bandeja → Reiniciar núcleo)."}
    </div>
  {/if}
</div>

<style>
  /* Margen transparente alrededor: ahí caben la ondulación del borde y la sombra (si no,
     quedarían cortadas en recto) y sirve para redimensionar la ventana. */
  .window {
    position: absolute;
    inset: 14px;
    display: flex;
    flex-direction: column;
    border-radius: 28px;
    overflow: hidden;
  }

  .maximized {
    inset: 0;
    border-radius: 0;
  }

  .titlebar {
    display: flex;
    flex: none;
    align-items: center;
    justify-content: space-between;
    height: 52px;
    padding: 0 16px 0 24px;
  }

  .title {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-secondary);
  }

  .buttons {
    display: flex;
    gap: 8px;
    opacity: 0;
    transition: opacity 160ms ease;
  }

  /* Los tres botones aparecen al pasar el ratón por la barra de título (SPEC sección 13). */
  .titlebar:hover .buttons,
  .buttons:focus-within {
    opacity: 1;
  }

  .buttons button {
    display: grid;
    place-items: center;
    width: 26px;
    height: 26px;
    padding: 0;
    border: none;
    border-radius: 50%;
    background: var(--control);
    color: var(--text-secondary);
    cursor: pointer;
  }

  .buttons button:hover {
    color: var(--text);
    filter: brightness(1.2);
  }

  .body {
    display: flex;
    flex: 1;
    min-height: 0;
  }

  nav {
    display: flex;
    flex: none;
    flex-direction: column;
    gap: 4px;
    width: 210px;
    padding: 4px 12px 20px 16px;
  }

  nav button {
    padding: 9px 14px;
    border: none;
    border-radius: 999px;
    background: transparent;
    color: inherit;
    font: inherit;
    font-size: 14px;
    text-align: left;
    cursor: pointer;
    transition: background 160ms ease;
  }

  nav button:hover {
    background: var(--control);
  }

  nav button.on {
    background: var(--glass-raised);
    font-weight: 600;
  }

  main {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: 22px;
    min-width: 0;
    padding: 4px 28px 32px 12px;
    overflow-y: auto;
    scrollbar-width: thin;
    scrollbar-color: var(--control) transparent;
  }

  h2 {
    margin: 0 0 -4px 16px;
    font-family: "Segoe UI Variable Display", "Segoe UI", system-ui, sans-serif;
    font-size: 26px;
    font-weight: 600;
  }

  .status {
    margin: 0 16px;
    color: var(--text-secondary);
  }

  .toast {
    position: absolute;
    left: 50%;
    bottom: 18px;
    translate: -50% 0;
    max-width: 80%;
    padding: 10px 18px;
    border-radius: 999px;
    background: var(--control-active);
    color: var(--text-on-active);
    font-size: 13px;
    box-shadow: var(--shadow);
  }
</style>
