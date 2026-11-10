<!--
  Burbuja de prueba del motor de cristal en una ventana sin foco, siempre encima y que deja
  pasar los clics (como la isla). Recibe las opciones de la galería y muestra su propio
  nivel y coste, porque es la ventana en la que el Acrylic de Windows fallaba.
-->
<script lang="ts">
  import { onMount } from "svelte";
  import { getCurrentWebviewWindow } from "@tauri-apps/api/webviewWindow";
  import { glass, glassShape, type GlassOptions, type GlassStats } from "$lib/glass";

  let stats = $state<GlassStats | null>(null);

  const fmt = (n: number, digits = 1) =>
    n.toLocaleString("es-ES", { maximumFractionDigits: digits });

  onMount(() => {
    void glass.attach();
    const unStats = glass.onStats((s) => (stats = s));
    const unOptions = getCurrentWebviewWindow().listen<GlassOptions>("glass-gallery-options", (e) =>
      glass.set(e.payload),
    );
    return () => {
      void unStats.then((f) => f());
      void unOptions.then((f) => f());
      glass.detach();
    };
  });
</script>

<main>
  <div class="bubble" use:glassShape={{ radius: 26 }}>
    <span class="display">Hallo</span>
    <span class="secondary">hola · alemán</span>
    <span class="tertiary">
      {#if stats?.failed}
        sin motor · tinte de CSS
      {:else if stats}
        ventana sin foco · {stats.effective}{stats.reason ? ` (${stats.reason})` : ""} · {fmt(
          stats.fps,
          0,
        )} fps
      {/if}
    </span>
  </div>
</main>

<style>
  main {
    display: flex;
    justify-content: center;
    padding: 30px 40px 60px;
    height: 100%;
  }

  .bubble {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2px;
    width: 420px;
    height: 130px;
    border-radius: 26px;
  }

  .display {
    font-family: "Segoe UI Variable Display", "Segoe UI", system-ui, sans-serif;
    font-size: 30px;
    font-weight: 600;
  }

  .secondary {
    font-size: 13px;
    color: var(--text-secondary);
  }

  .tertiary {
    margin-top: 4px;
    font-size: 11px;
    color: var(--text-tertiary);
  }
</style>
