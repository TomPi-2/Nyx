<!--
  Instalador de Nyx (9.08), con las pantallas del prototipo aprobado
  (docs/prototipos/instalador.html): bienvenida, licencia libre explicada en tres líneas,
  opciones (Everything y el acceso directo apagados), instalación con el progreso real y, al
  acabar, se recoge hacia arriba a la derecha (donde aparece el panel de descargas de Nyx) y
  abre Nyx, que guía el primer arranque.
-->
<script lang="ts">
  import { onMount } from "svelte";
  import { invoke } from "@tauri-apps/api/core";
  import { listen } from "@tauri-apps/api/event";
  import { getCurrentWindow, LogicalSize } from "@tauri-apps/api/window";
  import { glass, glassShape } from "$lib/glass";
  import NyxMark from "./NyxMark.svelte";

  type Screen = "welcome" | "license" | "options" | "install" | "done";

  interface Progress {
    key: string;
    label: string;
    done_mb: number;
    total_mb: number;
    finished: boolean;
    error: string | null;
  }

  /** Tamaños orientativos (GB) de lo que se instala, como en el prototipo. */
  const PARTS = [
    { what: "Nyx", hint: "La app y su núcleo", gb: 1.1 },
    { what: "Oído y voz", hint: "Whisper y la voz de Nyx", gb: 1.5 },
    { what: "Ollama", hint: "Lo que hace funcionar mi cerebro (si no lo tienes)", gb: 1.0 },
    { what: "Cerebro", hint: "Nyx 7B, en tu tarjeta gráfica", gb: 4.7 },
  ];
  const NEED_GB = PARTS.reduce((a, p) => a + p.gb, 0);

  // Solo en desarrollo: `?pantalla=options` para ver cada pantalla sin instalar nada.
  const preview = import.meta.env.DEV
    ? (new URLSearchParams(location.search).get("pantalla") as Screen | null)
    : null;
  let screen = $state<Screen>(preview ?? "welcome");
  let options = $state({ everything: false, autostart: true, shortcut: false });
  let free = $state<number | null>(null);
  let parts = $state<Record<string, Progress>>({});
  /** Un fallo con su código (docs/CODIGOS-DE-ERROR.md) para buscarlo en la web. */
  interface Fail {
    code: string | null;
    message: string;
    detail: string;
  }
  let error = $state<Fail | null>(
    preview && new URLSearchParams(location.search).has("fallo")
      ? { code: "I-110", message: "La instalación de Nyx ha fallado", detail: "exit 1" }
      : null,
  );
  let leaving = $state(false);

  const app = $derived(parts["app"]);
  const voice = $derived(Object.values(parts).filter((p) => p.key !== "app"));
  const voiceTotal = $derived(voice.reduce((a, p) => a + p.total_mb, 0));
  const voiceDone = $derived(voice.reduce((a, p) => a + Math.min(p.done_mb, p.total_mb), 0));
  const voiceFinished = $derived(voice.length > 0 && voice.every((p) => p.finished));
  /** Lo hecho de todo (0–1): la forma de Nyx se llena con esto. */
  const overall = $derived(
    ((app?.finished ? 1 : 0) * 0.4 + (voiceTotal > 0 ? (voiceDone / voiceTotal) * 0.6 : 0)) *
      (screen === "done" ? 0 : 1) +
      (screen === "done" ? 1 : 0),
  );

  const gb = (v: number) => `${v.toFixed(1).replace(".", ",")} GB`;
  const pct = (done: number, total: number) =>
    total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;

  async function start() {
    screen = "install";
    error = null;
    try {
      await invoke("install", { options });
      screen = "done";
      // Se recoge hacia arriba a la derecha, donde Nyx enseña lo que queda por bajar.
      setTimeout(() => {
        leaving = true;
        glass.follow(800); // el cristal sigue a la tarjeta mientras se recoge
      }, 900);
      setTimeout(() => void invoke("launch_nyx").catch((e) => (error = asFail(e))), 1600);
    } catch (e) {
      error = asFail(e);
    }
  }

  function asFail(e: unknown): Fail {
    if (e && typeof e === "object" && "code" in e && "message" in e) return e as Fail;
    return { code: null, message: "Algo ha fallado", detail: String(e) };
  }

  /** Margen alrededor de la tarjeta para su sombra y su borde líquido (ventana transparente). */
  const MARGIN = 36;
  let card: HTMLElement | undefined = $state();

  // La ventana mide lo que la tarjeta: lo transparente de alrededor no tapa clics.
  $effect(() => {
    if (!card || preview) return;
    const fit = new ResizeObserver(() => {
      if (!card || leaving) return;
      const r = card.getBoundingClientRect();
      const win = getCurrentWindow();
      void win
        .setSize(new LogicalSize(Math.ceil(r.width) + 2 * MARGIN, Math.ceil(r.height) + 2 * MARGIN))
        .then(() => win.center());
    });
    fit.observe(card);
    return () => fit.disconnect();
  });

  onMount(() => {
    // El cristal de la app, con el borde siempre en movimiento. Si la tarjeta gráfica no
    // puede, `<html data-glass="css">` y la tarjeta lleva el tinte de siempre.
    void glass.attach({
      quality: "auto",
      motion: "siempre",
      dark: matchMedia("(prefers-color-scheme: dark)").matches,
      lowOpacity: 0.96,
    });
    void invoke<number | null>("disk_free_gb").then((v) => (free = v));
    const off = listen<Progress>("install://progress", (e) => {
      parts = { ...parts, [e.payload.key]: e.payload };
    });
    return () => {
      void off.then((f) => f());
      glass.detach();
    };
  });

  function drag(event: MouseEvent) {
    if ((event.target as HTMLElement).closest("button, .toggle")) return;
    void getCurrentWindow().startDragging();
  }
</script>

<div class="stage">
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <main
    class="card"
    class:to-corner={leaving}
    onmousedown={drag}
    bind:this={card}
    use:glassShape={{ radius: 28 }}
  >
    {#if screen === "welcome"}
      <div class="head step-in">
        <NyxMark />
        <div>
          <div class="title">Hola, soy Nyx</div>
          <div class="sub">
            Tu asistente de voz para Windows. Funciono en tu PC, gratis y sin cuenta.
          </div>
        </div>
      </div>
      <p class="sub step-in">
        Voy a instalarme con lo recomendado para tu equipo. En cuanto pueda hablar, te pregunto cómo
        me quieres mientras termino.
      </p>
      <div class="actions">
        <button class="btn link" onclick={() => (screen = "options")}>Opciones</button>
        <span class="spacer"></span>
        <button class="btn primary" onclick={() => (screen = "license")}>Instalar</button>
      </div>
      <div class="dots"><i class="on"></i><i></i><i></i></div>
    {:else if screen === "license"}
      <div class="title step-in">Software libre</div>
      <div class="rows step-in">
        <div class="row">Puedes usar Nyx para lo que quieras, gratis.</div>
        <div class="row">Su código es público: cualquiera puede revisarlo y mejorarlo.</div>
        <div class="row">Si lo compartes cambiado, con la misma licencia (GPL-3.0).</div>
      </div>
      <div class="actions">
        <button class="btn link" onclick={() => void invoke("open_license")}
          >Leer la licencia</button
        >
        <span class="spacer"></span>
        <button class="btn" onclick={() => (screen = "welcome")}>Atrás</button>
        <button class="btn primary" onclick={start}>Continuar</button>
      </div>
      <div class="dots"><i></i><i class="on"></i><i></i></div>
    {:else if screen === "options"}
      <div class="title step-in">Qué se instala</div>
      <div class="rows step-in">
        {#each PARTS as part (part.what)}
          <div class="row">
            <div class="grow">
              <div class="what">{part.what}</div>
              <div class="hint">{part.hint}</div>
            </div>
            <span class="size">{gb(part.gb)}</span>
          </div>
        {/each}
        {#each [["everything", "Buscar en todo el disco (Everything)", "Gratis, de voidtools. Pide permiso de administrador una vez"], ["autostart", "Arrancar con Windows", "Para que esté lista al encender"], ["shortcut", "Acceso directo en el escritorio", "Siempre estoy en el menú Inicio y en la bandeja"]] as const as [key, what, hint] (key)}
          <div class="row">
            <div class="grow">
              <div class="what">{what}</div>
              <div class="hint">{hint}</div>
            </div>
            <button
              class="toggle"
              class:on={options[key]}
              role="switch"
              aria-checked={options[key]}
              aria-label={what}
              onclick={() => (options[key] = !options[key])}
            ></button>
          </div>
        {/each}
      </div>
      <div class="sub">
        Necesito unos {gb(NEED_GB)}{#if free !== null}
          · tienes {gb(free)} libres{/if}. Va a tu carpeta de usuario, sin administrador.
      </div>
      <div class="actions">
        <button class="btn" onclick={() => (screen = "welcome")}>Atrás</button>
        <span class="spacer"></span>
        <button class="btn primary" onclick={() => (screen = "license")}>Instalar</button>
      </div>
      <div class="dots"><i></i><i class="on"></i><i></i></div>
    {:else}
      <div class="head step-in">
        <NyxMark fill={screen === "done" ? 1 : overall} />
        <div>
          <div class="title">{screen === "done" ? "Ya puedo hablar" : "Instalando"}</div>
          <div class="sub">
            {#if error}
              {error.message}
            {:else if screen === "done"}
              Te espero arriba. Lo que falta lo bajo mientras te pregunto cómo me quieres.
            {:else}
              {Math.round(overall * 100)} %
            {/if}
          </div>
        </div>
      </div>
      <div class="rows">
        <div class="row">
          <div class="grow">
            <div class="what">Nyx</div>
            <div class="hint">La app y su núcleo</div>
            <div class="track">
              <div
                class="done"
                class:idle={!app || app.finished}
                class:busy={app && !app.finished && app.total_mb <= 1}
                style:--p="{app ? pct(app.done_mb, app.total_mb) : 0}%"
              ></div>
            </div>
          </div>
          <span class="state">
            {#if app?.error}Error{:else if app?.finished}<span class="tick">✓</span
              >{:else if app}Instalando{:else}En espera{/if}
          </span>
        </div>
        <div class="row">
          <div class="grow">
            <div class="what">Oído y voz</div>
            <div class="hint">Whisper y la voz de Nyx</div>
            <div class="track">
              <div
                class="done"
                class:idle={voiceFinished || voice.length === 0}
                style:--p="{pct(voiceDone, voiceTotal)}%"
              ></div>
            </div>
          </div>
          <span class="state">
            {#if voiceFinished}<span class="tick">✓</span>{:else if voice.length}{pct(
                voiceDone,
                voiceTotal,
              )} %{:else}En espera{/if}
          </span>
        </div>
      </div>
      {#if error}
        <div class="fail">
          <span class="code">{error.code ? `Código ${error.code}` : "Sin código"}</span>
          {#if error.code}
            <button
              class="btn link"
              onclick={() => void invoke("open_error", { code: error?.code ?? "" })}
              >Qué hacer</button
            >
          {/if}
        </div>
      {/if}
      <div class="actions">
        <span class="spacer"></span>
        {#if error}
          <button class="btn" onclick={() => void getCurrentWindow().close()}>Cerrar</button>
          <button class="btn primary" onclick={start}>Reintentar</button>
        {/if}
      </div>
      <div class="dots"><i></i><i></i><i class="on"></i></div>
    {/if}
  </main>
</div>

<style>
  .stage {
    height: 100%;
    display: grid;
    place-items: center;
  }

  /* Con el motor, el cristal lo dibuja él detrás (con su sombra y su borde líquido); sin él,
     el tinte de CSS de siempre. */
  .card {
    width: 440px;
    padding: 26px 28px 22px;
    display: grid;
    gap: 16px;
    border-radius: 28px;
    background: var(--tint);
    box-shadow: 0 18px 50px rgba(0, 0, 0, 0.3);
  }

  :global(html[data-glass="engine"]) .card {
    background: transparent;
    box-shadow: none;
  }

  .card {
    transition:
      transform 0.6s cubic-bezier(0.4, 0, 0.2, 1),
      opacity 0.45s;
  }

  /* Se recoge hacia el panel de descargas de Nyx (arriba a la derecha). */
  .card.to-corner {
    transform: translate(120px, -160px) scale(0.3);
    opacity: 0;
  }

  .head {
    display: flex;
    gap: 14px;
    align-items: center;
  }

  .title {
    font:
      600 22px/1.15 var(--display),
      sans-serif;
  }

  .sub {
    margin: 0;
    font-size: 13px;
    color: var(--text-2);
    line-height: 1.45;
  }

  .actions {
    display: flex;
    gap: 8px;
    align-items: center;
  }

  .spacer {
    flex: 1;
  }

  .btn {
    border: 0;
    border-radius: 999px;
    padding: 9px 18px;
    font: inherit;
    font-size: 14px;
    cursor: pointer;
    background: var(--control);
    color: var(--text);
    transition:
      transform 0.15s,
      opacity 0.2s;
    white-space: nowrap;
  }

  .btn:active {
    transform: scale(0.96);
  }

  .btn.primary {
    background: var(--active);
    color: var(--on-active);
    font-weight: 600;
  }

  .btn.link {
    background: transparent;
    color: var(--text-2);
    padding: 9px 6px;
  }

  .rows {
    display: grid;
    gap: 6px;
  }

  .row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 14px;
    border-radius: 16px;
    background: var(--raised);
    font-size: 13px;
  }

  .grow {
    flex: 1;
    min-width: 0;
  }

  .what {
    font-weight: 600;
    font-size: 13.5px;
  }

  .hint {
    color: var(--text-2);
    font-size: 12px;
  }

  .size {
    color: var(--text-2);
    font-variant-numeric: tabular-nums;
  }

  .toggle {
    width: 38px;
    height: 22px;
    border: 0;
    padding: 0;
    border-radius: 999px;
    background: var(--control-hi);
    position: relative;
    flex: none;
    cursor: pointer;
  }

  .toggle::after {
    content: "";
    position: absolute;
    top: 3px;
    left: 3px;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--text);
    transition: left 0.25s;
  }

  .toggle.on {
    background: var(--active);
  }

  .toggle.on::after {
    left: 19px;
    background: var(--on-active);
  }

  /* Barras líquidas, sin bordes; la parte hecha brilla mientras avanza. */
  .track {
    height: 6px;
    border-radius: 999px;
    background: var(--control);
    overflow: hidden;
    margin-top: 6px;
  }

  .track .done {
    height: 100%;
    width: var(--p, 0%);
    border-radius: 999px;
    background: var(--fill);
    transition: width 0.35s ease;
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

  .track .done.idle {
    animation: none;
    background-image: none;
  }

  /* Sin saber cuánto falta (el Setup de Velopack no lo dice): una franja que va y viene. */
  .track .done.busy {
    width: 35%;
    animation: busy 1.3s ease-in-out infinite alternate;
  }

  @keyframes shine {
    from {
      background-position: -60px 0;
    }
    to {
      background-position: 260px 0;
    }
  }

  @keyframes busy {
    from {
      transform: translateX(-10%);
    }
    to {
      transform: translateX(200%);
    }
  }

  .fail {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 6px 6px 14px;
    border-radius: 16px;
    background: var(--raised);
    font-size: 12.5px;
  }

  .fail .code {
    flex: 1;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }

  .state {
    font-size: 12px;
    color: var(--text-2);
    min-width: 64px;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }

  .tick {
    display: inline-block;
    width: 18px;
    height: 18px;
    border-radius: 50%;
    background: var(--active);
    color: var(--on-active);
    font-size: 12px;
    line-height: 18px;
    text-align: center;
    animation: popin 0.4s cubic-bezier(0.3, 1.6, 0.5, 1);
  }

  @keyframes popin {
    from {
      transform: scale(0);
    }
    to {
      transform: scale(1);
    }
  }

  .step-in {
    animation: stepin 0.45s cubic-bezier(0.3, 1.2, 0.5, 1) both;
  }

  @keyframes stepin {
    from {
      opacity: 0;
      transform: translateY(10px);
    }
    to {
      opacity: 1;
      transform: none;
    }
  }

  .dots {
    display: flex;
    gap: 6px;
    justify-content: center;
    align-items: center;
  }

  .dots i {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--control-hi);
  }

  .dots i.on {
    background: var(--text);
    width: 18px;
    border-radius: 999px;
  }

  @media (prefers-reduced-motion: reduce) {
    .track .done,
    .step-in,
    .tick {
      animation: none;
    }
  }
</style>
