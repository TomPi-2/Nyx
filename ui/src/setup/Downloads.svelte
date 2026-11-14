<!--
  Panel de descargas del primer arranque (9.10): arriba a la derecha del monitor de Nyx,
  mientras baja lo que falta (la voz, el cerebro…) con su progreso real (setup_progress). Se
  ve solo si de verdad baja algo; al acabar dice «Todo listo» y se va. Si se corta la red,
  lo dice y deja reintentar (la descarga sigue donde iba).
-->
<script lang="ts">
  import { onMount } from "svelte";
  import { invoke } from "@tauri-apps/api/core";
  import { connectCore, type CoreConnection } from "$lib/core";
  import { glass, glassFromSettings, glassPoke, glassShape } from "$lib/glass";
  import { POP_IN_MS, POP_OUT_MS } from "$lib/motion";
  import type { ServerMessage } from "$lib/protocol";
  import { applyAppearance } from "$theme/apply";
  import { PANEL_RADIUS } from "../overlay/panels/layout";

  const WIDTH = 280;
  const PAD = 24;
  /** «Todo listo» se queda este rato antes de irse. */
  const DONE_MS = 2600;

  interface Part {
    label: string;
    done: number;
    total: number;
    finished: boolean;
    error: string | null;
  }

  let parts = $state<Record<string, Part>>({});
  let connected = $state(false);
  let failed = $state<string | null>(null);
  let allDone = $state(false);
  let leaving = $state(false);
  let gone = $state(true);
  let panel: HTMLDivElement | undefined = $state();
  let core: CoreConnection | undefined;
  let doneTimer: ReturnType<typeof setTimeout> | undefined;

  const list = $derived(Object.entries(parts));
  const total = $derived(list.reduce((a, [, p]) => a + p.total, 0));
  const done = $derived(list.reduce((a, [, p]) => a + Math.min(p.done, p.total), 0));
  const percent = $derived(total > 0 ? Math.round((done / total) * 100) : 0);

  const visible = $derived(connected && !gone);
  /** Código del fallo (docs/CODIGOS-DE-ERROR.md), al principio del texto: «D-201 · …». */
  const code = $derived(failed?.match(/^([IDAN]-\d{3})\b/)?.[1] ?? null);
  /** Lo que ha pasado, sin el código delante. */
  const reason = $derived(failed?.replace(/^[IDAN]-\d{3}\s*·\s*/, "") ?? "");

  $effect(() => {
    void invoke("island_set_size", {
      width: WIDTH + 2 * PAD,
      height: 90 + list.length * 30 + 2 * PAD,
      top: 16,
      right: true,
    });
  });
  $effect(() => {
    void invoke("island_set_visible", { visible });
  });
  // Solo los botones reciben clics; el resto deja pasar el ratón.
  $effect(() => {
    void failed;
    void visible;
    requestAnimationFrame(() => {
      const buttons = visible && panel ? [...panel.querySelectorAll("button")] : [];
      const rects = buttons.map((b) => {
        const r = b.getBoundingClientRect();
        return [r.x, r.y, r.width, r.height];
      });
      void invoke("island_set_hit_rects", { rects });
    });
  });

  function progress(msg: Extract<ServerMessage, { type: "setup_progress" }>) {
    // Algo que ya estaba (0 de 0) no se enseña.
    if (msg.total_mb <= 0 && !msg.error) return;
    parts = {
      ...parts,
      [msg.key]: {
        label: labelOf(msg.key, msg.label),
        done: msg.done_mb,
        total: msg.total_mb,
        finished: msg.finished,
        error: msg.error,
      },
    };
    failed = msg.error;
    allDone = false;
    clearTimeout(doneTimer);
    if (gone) {
      gone = false;
      leaving = false;
      glass.poke();
      glass.follow(POP_IN_MS + 80);
    }
  }

  function finished(ok: boolean, message: string | null) {
    if (gone) return;
    if (!ok) {
      failed = message ?? "No se ha podido descargar";
      return;
    }
    allDone = true;
    doneTimer = setTimeout(() => {
      leaving = true;
      glass.follow(POP_OUT_MS + 40);
      setTimeout(() => {
        gone = true;
        parts = {};
      }, POP_OUT_MS);
    }, DONE_MS);
  }

  /** Nombres que se entienden: «Cerebro» en vez de «ollama:qwen2.5:7b». */
  function labelOf(key: string, label: string): string {
    if (key.startsWith("ollama:")) return "Cerebro";
    if (key === "stt") return "Oído";
    if (key.startsWith("voice") || key === "pocket") return "Voz";
    if (key.startsWith("wake") || key === "vad") return "Activación";
    return label;
  }

  function handle(msg: ServerMessage) {
    switch (msg.type) {
      case "welcome":
        applyAppearance(msg);
        if (msg.glass) glass.set(glassFromSettings(msg.glass, msg.panel_tint));
        break;
      case "settings":
        glass.set(glassFromSettings(msg.data.appearance.glass, msg.data.appearance.panel_tint));
        applyAppearance(msg.data.appearance);
        break;
      case "setup_progress":
        progress(msg);
        break;
      case "setup_result":
        if (msg.action === "download") finished(msg.ok, msg.message);
        break;
      case "game":
        glass.setGame(msg.active);
        break;
    }
  }

  function retry() {
    failed = null;
    core?.send({ type: "setup", action: "download" });
  }

  onMount(() => {
    void glass.attach();
    const connection = connectCore(handle, (ok) => (connected = ok));
    core = connection;
    return () => {
      connection.close();
      glass.detach();
    };
  });
</script>

{#if !gone}
  <div class="wrap" style:padding="{PAD}px">
    <div
      class="panel"
      class:pop-in={!leaving}
      class:pop-out={leaving}
      style:width="{WIDTH}px"
      bind:this={panel}
      use:glassShape={{ radius: PANEL_RADIUS }}
      use:glassPoke
    >
      <div class="head">
        <span class="title">
          {#if allDone}Todo listo{:else if failed}No he podido terminar{:else}Bajando lo que me
            falta{/if}
        </span>
        <span class="sub">
          {#if allDone}
            ✓ Ya lo tengo todo
          {:else if failed}
            {reason || "Sigo donde iba en cuanto vuelva."}
          {:else}
            {percent} %
          {/if}
        </span>
      </div>
      {#each list as [key, part] (key)}
        <div class="line">
          <span>{part.label}</span>
          <div class="track">
            <i
              class:moving={!part.finished && !failed}
              style:width="{part.total > 0 ? (part.done / part.total) * 100 : 0}%"
            ></i>
          </div>
          <span class="state">
            {#if part.finished && !part.error}✓{:else}{Math.round(
                part.total > 0 ? (part.done / part.total) * 100 : 0,
              )} %{/if}
          </span>
        </div>
      {/each}
      {#if failed}
        <div class="fail">
          {#if code}
            <span class="code">Código {code}</span>
            <button class="link" onclick={() => void invoke("open_error", { code })}
              >Qué hacer</button
            >
          {/if}
          <span class="spacer"></span>
          <button onclick={retry}>Reintentar</button>
        </div>
      {/if}
    </div>
  </div>
{/if}

<style>
  .wrap {
    display: flex;
    justify-content: flex-end;
  }

  .panel {
    display: grid;
    gap: 10px;
    padding: 14px 16px;
    border-radius: 22px;
    transform-origin: 100% 0;
  }

  .head {
    display: grid;
  }

  .title {
    font-size: 13px;
    font-weight: 600;
  }

  .sub {
    font-size: 12px;
    color: var(--text-secondary);
  }

  .line {
    display: grid;
    grid-template-columns: 70px 1fr 44px;
    gap: 8px;
    align-items: center;
    font-size: 12px;
    color: var(--text-secondary);
  }

  .track {
    height: 6px;
    border-radius: 999px;
    background: var(--control);
    overflow: hidden;
  }

  /* Líquida, sin bordes; la parte hecha brilla mientras avanza (como en el instalador). */
  .track i {
    display: block;
    height: 100%;
    border-radius: 999px;
    background: var(--control-active);
    transition: width 350ms ease;
  }

  .track i.moving {
    background-image: linear-gradient(
      90deg,
      transparent 0,
      rgba(255, 255, 255, 0.45) 50%,
      transparent 100%
    );
    background-size: 60px 100%;
    background-repeat: no-repeat;
    animation: shine 1.4s linear infinite;
  }

  @keyframes shine {
    from {
      background-position: -60px 0;
    }
    to {
      background-position: 260px 0;
    }
  }

  .state {
    text-align: right;
    font-variant-numeric: tabular-nums;
  }

  .fail {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
  }

  .fail .code {
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }

  .spacer {
    flex: 1;
  }

  button.link {
    background: transparent;
    color: var(--text-secondary);
    padding: 6px 4px;
  }

  button {
    justify-self: end;
    padding: 6px 12px;
    border: none;
    border-radius: 999px;
    background: var(--control);
    color: var(--text);
    font: inherit;
    font-size: 12.5px;
    cursor: pointer;
  }

  @media (prefers-reduced-motion: reduce) {
    .track i.moving {
      animation: none;
    }
  }
</style>
