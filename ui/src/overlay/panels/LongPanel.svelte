<!--
  Panel de respuesta larga (6.28, prototipo docs/prototipos/panel-largo.html aprobado):

  - Explicación por voz: cada frase se escribe letra a letra mientras suena, repartida por lo
    que dura su audio (`chunks`, del núcleo); nunca va por delante de la voz y no se borra nada.
    El panel crece hasta su alto máximo y luego sigue la lectura, salvo que el usuario suba
    para releer (entonces «Seguir leyendo»).
  - Escrita: todo de golpe.
  - Receta, pasos o lista: secciones con viñetas o numeradas, de golpe.

  Botones: Guardar en una nota, Copiar y Cerrar; tras guardar, el aviso con Deshacer.
-->
<script lang="ts" module>
  export interface Chunk {
    text: string;
    /** Lo que dura su audio (ms); 0: de golpe (lo dicho antes de pasar al panel largo). */
    durationMs: number;
    /** Cuándo llegó (performance.now()): empieza a sonar en ese momento. */
    at: number;
  }
</script>

<script lang="ts">
  import { onMount, tick } from "svelte";
  import { glassPoke, glassShape } from "$lib/glass";
  import type { LongSection } from "$lib/protocol";
  import { PANEL_MAX_WIDTH, PANEL_RADIUS } from "./layout";

  interface Props {
    title: string;
    meta?: string | null;
    text?: string;
    sections?: LongSection[];
    chunks?: Chunk[];
    note?: string;
    /** Con un id, el pie enseña el aviso y «Deshacer» (tras guardar la nota). */
    undoAction?: string | null;
    onaction?: (id: string) => void;
  }
  let {
    title,
    meta = null,
    text = "",
    sections = [],
    chunks = [],
    note = "",
    undoAction = null,
    onaction,
  }: Props = $props();

  /** Letras escritas de cada frase. */
  let shown = $state<number[]>([]);
  let typing = $state(false);
  let follow = $state(true);
  let scroller: HTMLDivElement | undefined = $state();

  /** Cuántas letras de la frase `i` deben verse ya: al ritmo de su audio; si ya ha llegado
   *  la siguiente, entera (la voz ya va por ella). */
  function due(i: number, now: number): number {
    const c = chunks[i];
    if (!c) return 0;
    if (c.durationMs <= 0 || i < chunks.length - 1) return c.text.length;
    return Math.min(c.text.length, Math.floor(((now - c.at) / c.durationMs) * c.text.length));
  }

  onMount(() => {
    let frame = 0;
    const step = () => {
      const now = performance.now();
      let changed = false;
      const next = chunks.map((_, i) => {
        const value = Math.max(shown[i] ?? 0, due(i, now));
        if (value !== (shown[i] ?? 0)) changed = true;
        return value;
      });
      if (changed || next.length !== shown.length) {
        shown = next;
        if (follow) void tick().then(toBottom);
      }
      typing = chunks.some((c, i) => (next[i] ?? 0) < c.text.length);
      frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  });

  function toBottom() {
    if (scroller) scroller.scrollTop = scroller.scrollHeight;
  }

  function onwheel(e: WheelEvent) {
    if (e.deltaY < 0) follow = false;
  }

  function onscroll() {
    if (!scroller) return;
    if (scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 4) follow = true;
  }

  function resume() {
    follow = true;
    toBottom();
  }

  const reading = $derived(chunks.length > 0);
  const lastTyping = $derived(typing ? chunks.length - 1 : -1);
</script>

<!-- data-hit: todo el panel recibe el ratón (rueda para releer, el puntero encima para el tiempo). -->
<div
  class="panel"
  data-hit
  style:width="{PANEL_MAX_WIDTH}px"
  use:glassShape={{ radius: PANEL_RADIUS }}
  use:glassPoke
>
  {#if title || meta}
    <header>
      {#if title}<span class="title">{title}</span>{/if}
      {#if meta}<span class="meta">{meta}</span>{/if}
    </header>
  {/if}

  <div class="scroller" bind:this={scroller} {onwheel} {onscroll}>
    {#if sections.length}
      <div class="struct">
        {#each sections as section, i (i)}
          {#if section.title}<h3>{section.title}</h3>{/if}
          {#if section.ordered}
            <ol>
              {#each section.items as item, j (j)}<li>{item}</li>{/each}
            </ol>
          {:else}
            <ul>
              {#each section.items as item, j (j)}<li>{item}</li>{/each}
            </ul>
          {/if}
        {/each}
      </div>
    {:else if reading}
      <p class="body">
        {#each chunks as chunk, i (i)}
          <span class="s" class:now={i === chunks.length - 1 && typing}
            >{chunk.text.slice(0, shown[i] ?? 0)}{" "}</span
          >{#if i === lastTyping}<span class="caret"></span>{/if}
        {/each}
      </p>
    {:else}
      <p class="body">{text}</p>
    {/if}
    {#if !follow}
      <button class="follow" onclick={resume}>Seguir leyendo ↓</button>
    {/if}
  </div>

  <footer>
    {#if undoAction}
      <span class="note grow">{note}</span>
      <button class="pill" onclick={() => onaction?.(undoAction ?? "")}>Deshacer</button>
      <button class="pill" onclick={() => onaction?.("long-close")}>Cerrar</button>
    {:else}
      <button class="pill primary" onclick={() => onaction?.("long-save")}>
        Guardar en una nota
      </button>
      <button class="pill" onclick={() => onaction?.("long-copy")}>Copiar</button>
      <button class="pill" onclick={() => onaction?.("long-close")}>Cerrar</button>
      {#if note}<span class="note">{note}</span>{/if}
    {/if}
  </footer>
</div>

<style>
  .panel {
    display: flex;
    flex-direction: column;
    max-width: 100%;
    max-height: 480px;
    border-radius: 26px;
  }

  header {
    display: grid;
    gap: 2px;
    padding: 18px 22px 6px;
    text-align: center;
  }

  .title {
    font-family: var(--font-display);
    font-size: 20px;
    font-weight: 600;
    line-height: 1.2;
  }

  .meta {
    font-size: 12px;
    color: var(--text-tertiary);
  }

  .scroller {
    position: relative;
    min-height: 0;
    padding: 4px 22px 8px;
    overflow-y: auto;
    overscroll-behavior: contain;
    user-select: text;
  }

  .body {
    margin: 0 0 6px;
    font-size: 15px;
    line-height: 1.55;
    white-space: pre-line;
  }

  /* Lo ya dicho, un poco más apagado; la frase que suena, con todo el brillo. */
  .s {
    color: var(--text-secondary);
    transition: color 400ms ease;
  }

  .s.now {
    color: var(--text);
  }

  .caret {
    display: inline-block;
    width: 2px;
    height: 1em;
    margin-left: 1px;
    vertical-align: -0.15em;
    background: var(--text-secondary);
    animation: blink 1s steps(1) infinite;
  }

  @keyframes blink {
    50% {
      opacity: 0;
    }
  }

  .struct h3 {
    margin: 14px 0 6px;
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--text-secondary);
  }

  .struct h3:first-child {
    margin-top: 4px;
  }

  .struct ul,
  .struct ol {
    display: grid;
    gap: 5px;
    margin: 0;
    padding-left: 22px;
    font-size: 15px;
    line-height: 1.45;
  }

  .struct li::marker {
    color: var(--text-tertiary);
  }

  .follow {
    position: sticky;
    bottom: 6px;
    display: block;
    margin: 0 auto;
    padding: 6px 14px;
    border: none;
    border-radius: 999px;
    background: var(--control-active);
    color: var(--text-on-active);
    font: inherit;
    font-size: 12px;
    cursor: pointer;
  }

  footer {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    padding: 10px 14px 14px;
  }

  .pill {
    padding: 9px 16px;
    border: none;
    border-radius: 999px;
    background: var(--control);
    color: inherit;
    font: inherit;
    font-size: 14px;
    cursor: pointer;
    transition: transform 120ms ease;
  }

  .pill:active {
    transform: scale(0.97);
  }

  .primary {
    background: var(--control-active);
    color: var(--text-on-active);
    font-weight: 600;
  }

  .note {
    margin-left: auto;
    padding-right: 6px;
    font-size: 12px;
    color: var(--text-tertiary);
  }

  .note.grow {
    flex: 1;
    margin-left: 0;
    padding: 0 8px;
    font-size: 13px;
    color: var(--text-secondary);
  }

  @media (prefers-reduced-motion: reduce) {
    .caret {
      animation: none;
    }
  }
</style>
