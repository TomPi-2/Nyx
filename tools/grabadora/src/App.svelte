<!--
  Grabadora de la voz de Nyx (2026-11-15). Pensada para alguien que no sabe de ordenadores:
  la frase en grande, cómo decirla, cuatro botones grandes y, tras cada toma, si algo ha
  salido mal, en palabras sencillas. Quien dirige va por Discord: «otra vez», «siguiente».

  Teclado: Espacio graba y para · Intro o → siguiente · ← anterior · E escuchar · R otra vez.
-->
<script lang="ts">
  import { onMount } from "svelte";
  import { invoke } from "@tauri-apps/api/core";
  import guion from "./guion.json";

  interface Linea {
    id: string;
    sesion: number;
    texto: string;
    tono: string;
    fuente: string;
    /** Idioma de lo que va entre comillas («es» si todo es español) y cómo se pronuncia. */
    idioma?: string;
    pista?: string;
  }
  const IDIOMAS: Record<string, string> = {
    en: "inglés",
    fr: "francés",
    it: "italiano",
    de: "alemán",
    pt: "portugués",
    marca: "nombre en su idioma",
  };
  interface Analysis {
    seconds: number;
    peak_db: number;
    speech_db: number;
    noise_db: number;
    lead_s: number;
    tail_s: number;
    clipped: boolean;
    quiet: boolean;
    noisy: boolean;
    cut_start: boolean;
    cut_end: boolean;
    empty: boolean;
  }
  interface Status {
    level: number;
    seconds: number;
    speech: boolean;
    silence_ms: number;
    error: string | null;
  }

  const LINEAS = guion as Linea[];
  const SESIONES = Math.max(...LINEAS.map((l) => l.sesion));
  /** Silencio tras hablar con el que la toma se para sola. */
  const STOP_AFTER_MS = 1300;
  /** Por si se queda grabando sin querer. */
  const MAX_S = 30;

  const TONOS: Record<string, string> = {
    natural: "Natural, como si se lo contaras a alguien",
    cercana: "Cercana y amable, como Nyx",
    alegre: "Alegre, con ganas",
    pregunta: "Preguntando de verdad",
    tranquila: "Tranquila, sin prisa",
  };

  // Solo en desarrollo: `?pantalla=grabar` para verla sin micrófono.
  const preview = import.meta.env.DEV && location.search.includes("pantalla=grabar");
  let screen = $state<"mic" | "grabar">(preview ? "grabar" : "mic");
  let mics = $state<string[]>([]);
  let mic = $state<string | null>(null);
  let sesion = $state(1);
  let frase = $state(0);
  let grabadas = $state<Set<string>>(new Set());
  let recording = $state(false);
  let level = $state(0);
  let seconds = $state(0);
  let last = $state<{ analysis: Analysis; takes: number } | null>(null);
  let error = $state<string | null>(null);
  let busy = $state(false);
  let poll: ReturnType<typeof setInterval> | undefined;
  let audio: HTMLAudioElement | undefined;

  const lineas = $derived(LINEAS.filter((l) => l.sesion === sesion));
  const linea = $derived(lineas[Math.min(frase, lineas.length - 1)]);
  const hechas = $derived(lineas.filter((l) => grabadas.has(l.id)).length);
  const grabada = $derived(linea ? grabadas.has(linea.id) : false);

  /** Lo que ha salido mal en la toma, en palabras sencillas (lo más grave primero). */
  const avisos = $derived.by(() => {
    const a = last?.analysis;
    if (!a) return [];
    const out: string[] = [];
    if (a.empty) out.push("No se te ha oído. ¿Está bien el micrófono? Prueba otra vez.");
    if (a.clipped) out.push("Ha sonado demasiado fuerte. Aléjate un poco del micrófono.");
    if (a.quiet) out.push("Ha sonado bajito. Acércate un poco o habla con más fuerza.");
    if (a.cut_start) out.push("Has empezado a hablar demasiado pronto. Espera un segundo.");
    if (a.cut_end) out.push("Se ha cortado el final. Espera un segundo antes de parar.");
    if (a.noisy) out.push("Hay ruido de fondo. ¿Algo encendido cerca?");
    return out;
  });

  onMount(() => {
    void (async () => {
      const progress = await invoke<{ sesion: number; frase: number; mic: string | null }>(
        "load_progress",
      );
      const list = await invoke<{ names: string[]; default: string | null }>("mics");
      mics = list.names;
      mic = progress.mic && list.names.includes(progress.mic) ? progress.mic : list.default;
      sesion = Math.min(Math.max(1, progress.sesion), SESIONES);
      frase = Math.max(0, progress.frase);
      await refresh();
      if (progress.mic && list.names.includes(progress.mic)) screen = "grabar";
    })();
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      clearInterval(poll);
      void invoke("cancel");
    };
  });

  async function refresh() {
    grabadas = new Set(await invoke<string[]>("recorded", { sesion }));
  }

  function save() {
    void invoke("save_progress", { progress: { sesion, frase, mic } });
  }

  async function record() {
    if (recording || busy || !linea) return;
    stopAudio();
    error = null;
    last = null;
    try {
      await invoke("start", { mic });
    } catch (e) {
      error = String(e);
      return;
    }
    recording = true;
    seconds = 0;
    poll = setInterval(async () => {
      const s = await invoke<Status | null>("status");
      if (!s) return;
      level = s.level;
      seconds = s.seconds;
      if (s.error) {
        error = s.error;
        void stop();
      } else if ((s.speech && s.silence_ms >= STOP_AFTER_MS) || s.seconds >= MAX_S) {
        void stop();
      }
    }, 50);
  }

  async function stop() {
    if (!recording || !linea) return;
    clearInterval(poll);
    recording = false;
    level = 0;
    busy = true;
    try {
      last = await invoke("stop", { sesion, id: linea.id, texto: linea.texto });
      await refresh();
    } catch (e) {
      error = String(e);
    } finally {
      busy = false;
    }
  }

  async function listen() {
    if (!linea || recording) return;
    stopAudio();
    try {
      const bytes = await invoke<ArrayBuffer>("take_audio", { sesion, id: linea.id });
      audio = new Audio(URL.createObjectURL(new Blob([bytes], { type: "audio/wav" })));
      void audio.play();
    } catch (e) {
      error = String(e);
    }
  }

  function stopAudio() {
    audio?.pause();
    audio = undefined;
  }

  function go(delta: number) {
    if (recording) return;
    stopAudio();
    last = null;
    error = null;
    frase = Math.min(Math.max(0, frase + delta), lineas.length - 1);
    save();
  }

  async function changeSession(delta: number) {
    if (recording) return;
    const next = Math.min(Math.max(1, sesion + delta), SESIONES);
    if (next === sesion) return;
    sesion = next;
    // Al cambiar de sesión, a la primera frase que falte.
    await refresh();
    const missing = lineas.findIndex((l) => !grabadas.has(l.id));
    frase = missing === -1 ? 0 : missing;
    last = null;
    save();
  }

  async function pack() {
    error = null;
    try {
      await invoke("pack", { sesion });
    } catch (e) {
      error = String(e);
    }
  }

  function onKey(e: KeyboardEvent) {
    if (screen !== "grabar" || e.repeat) return;
    if (e.code === "Space") {
      e.preventDefault();
      void (recording ? stop() : record());
    } else if (e.key === "Enter" || e.key === "ArrowRight") {
      go(1);
    } else if (e.key === "ArrowLeft") {
      go(-1);
    } else if (e.key.toLowerCase() === "e") {
      void listen();
    } else if (e.key.toLowerCase() === "r") {
      void record();
    }
  }

  // Nivel en dB para la barra: de -60 (nada) a 0 (lo máximo).
  const meter = $derived(
    Math.min(100, Math.max(0, ((20 * Math.log10(Math.max(level, 1e-6)) + 60) / 60) * 100)),
  );
</script>

<main>
  {#if screen === "mic"}
    <section class="card start">
      <h1>Hola</h1>
      <p class="sub">
        Aquí vas a grabar la voz de Nyx, frase a frase. Primero, elige tu micrófono: el mismo que
        usas en Discord.
      </p>
      <div class="pills" role="radiogroup" aria-label="Micrófono">
        {#each mics as name (name)}
          <button
            role="radio"
            aria-checked={mic === name}
            class:on={mic === name}
            onclick={() => (mic = name)}>{name}</button
          >
        {/each}
      </div>
      {#if mics.length === 0}
        <p class="warn">No encuentro ningún micrófono. Conéctalo y vuelve a abrir esto.</p>
      {/if}
      <div class="actions">
        <span class="spacer"></span>
        <button
          class="btn primary big"
          disabled={!mic}
          onclick={() => {
            screen = "grabar";
            save();
          }}>Empezar</button
        >
      </div>
    </section>
  {:else if linea}
    <header>
      <div class="session">
        <button class="btn small" onclick={() => changeSession(-1)} disabled={sesion === 1}
          >‹</button
        >
        <span>Sesión {sesion} de {SESIONES}</span>
        <button class="btn small" onclick={() => changeSession(1)} disabled={sesion === SESIONES}
          >›</button
        >
      </div>
      <div class="count">
        Frase {frase + 1} de {lineas.length} · grabadas {hechas}
        <div class="track"><i style:width="{(hechas / lineas.length) * 100}%"></i></div>
      </div>
      <button class="btn small" onclick={() => (screen = "mic")} disabled={recording}
        >Micrófono</button
      >
    </header>

    <section class="card line" class:rec={recording}>
      <div class="tone">{TONOS[linea.tono] ?? linea.tono}</div>
      <p class="text">{linea.texto}</p>
      {#if linea.pista}
        <!-- No se lee: cómo suena lo de otro idioma (con acento, sin exagerar). -->
        <p class="hint">
          {IDIOMAS[linea.idioma ?? ""] ?? linea.idioma}: suena «{linea.pista}» · no lo leas
        </p>
      {/if}
      <div class="meta">
        {#if recording}
          <span class="dot"></span> Grabando… {seconds.toFixed(1)} s
        {:else if busy}
          Guardando…
        {:else if grabada}
          ✓ Grabada{last ? ` (toma ${last.takes})` : ""}
        {:else}
          Pulsa «Grabar», espera un segundo y dila
        {/if}
      </div>
      <div class="meter" aria-hidden="true"><i style:width="{recording ? meter : 0}%"></i></div>
    </section>

    {#if error}
      <p class="warn">{error}</p>
    {:else if avisos.length}
      <ul class="avisos">
        {#each avisos as a (a)}<li>{a}</li>{/each}
      </ul>
    {:else if last}
      <p class="ok">¡Bien! Ha sonado limpia.</p>
    {/if}

    <div class="controls">
      <button class="btn" onclick={() => go(-1)} disabled={recording || frase === 0}
        >← Anterior</button
      >
      {#if recording}
        <button class="btn primary huge" onclick={stop}>■ Parar</button>
      {:else}
        <button class="btn primary huge" onclick={record} disabled={busy}
          >{grabada ? "↺ Otra vez" : "● Grabar"}</button
        >
      {/if}
      <button class="btn" onclick={listen} disabled={recording || !grabada}>▶ Escuchar</button>
      <button class="btn" onclick={() => go(1)} disabled={recording || frase >= lineas.length - 1}
        >Siguiente →</button
      >
    </div>

    <footer>
      <span class="keys">Espacio: grabar / parar · Intro: siguiente · E: escuchar</span>
      <span class="spacer"></span>
      <button class="btn small" onclick={() => invoke("open_folder")}>Abrir la carpeta</button>
      <button class="btn small" onclick={pack} disabled={recording || hechas === 0}
        >Preparar para enviar</button
      >
    </footer>
  {/if}
</main>

<style>
  main {
    height: 100%;
    box-sizing: border-box;
    padding: 22px 26px;
    display: grid;
    grid-template-rows: auto 1fr auto auto auto;
    gap: 16px;
  }

  .card {
    border-radius: 28px;
    background: var(--raised);
    padding: 26px 28px;
  }

  .start {
    align-self: center;
    justify-self: center;
    width: min(560px, 100%);
    display: grid;
    gap: 16px;
    grid-row: 1 / -1;
  }

  h1 {
    margin: 0;
    font: 600 26px/1.15 var(--display);
  }

  .sub {
    margin: 0;
    color: var(--text-2);
    line-height: 1.5;
  }

  header {
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .session {
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: 600;
  }

  .count {
    flex: 1;
    display: grid;
    gap: 6px;
    font-size: 13px;
    color: var(--text-2);
  }

  .track {
    height: 6px;
    border-radius: 999px;
    background: var(--control);
    overflow: hidden;
  }

  .track i {
    display: block;
    height: 100%;
    border-radius: 999px;
    background: var(--fill);
    transition: width 0.3s ease;
  }

  .line {
    display: grid;
    align-content: center;
    gap: 18px;
    text-align: center;
    transition: box-shadow 0.2s;
  }

  .line.rec {
    box-shadow: 0 0 0 3px var(--rec);
  }

  .tone {
    justify-self: center;
    padding: 6px 14px;
    border-radius: 999px;
    background: var(--control);
    font-size: 13px;
    color: var(--text-2);
  }

  .text {
    margin: 0;
    font: 500 30px/1.35 var(--display);
    text-wrap: balance;
  }

  .hint {
    margin: 10px 0 0;
    font-size: 15px;
    opacity: 0.7;
  }

  .meta {
    font-size: 14px;
    color: var(--text-2);
    display: flex;
    gap: 8px;
    align-items: center;
    justify-content: center;
    min-height: 1.4em;
  }

  .dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--rec);
    animation: pulse 1s ease-in-out infinite;
  }

  @keyframes pulse {
    50% {
      opacity: 0.35;
    }
  }

  .meter {
    height: 10px;
    border-radius: 999px;
    background: var(--control);
    overflow: hidden;
  }

  .meter i {
    display: block;
    height: 100%;
    border-radius: 999px;
    background: var(--fill);
    transition: width 60ms linear;
  }

  .avisos,
  .warn,
  .ok {
    margin: 0;
    padding: 12px 18px;
    border-radius: 18px;
    background: var(--raised);
    font-size: 15px;
  }

  .avisos {
    list-style: none;
    display: grid;
    gap: 4px;
  }

  .warn {
    color: var(--rec);
  }

  .ok {
    color: var(--text-2);
  }

  .controls {
    display: flex;
    gap: 10px;
    justify-content: center;
    align-items: center;
  }

  footer {
    display: flex;
    gap: 8px;
    align-items: center;
  }

  .keys {
    font-size: 12px;
    color: var(--text-3);
  }

  .spacer {
    flex: 1;
  }

  .actions {
    display: flex;
  }

  .pills {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .pills button {
    padding: 10px 16px;
    border: 0;
    border-radius: 999px;
    background: var(--control);
    color: var(--text);
    font: inherit;
    cursor: pointer;
  }

  .pills button.on {
    background: var(--active);
    color: var(--on-active);
    font-weight: 600;
  }

  .btn {
    border: 0;
    border-radius: 999px;
    padding: 12px 20px;
    font: inherit;
    font-size: 15px;
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

  .btn:disabled {
    opacity: 0.35;
    cursor: default;
  }

  .btn.primary {
    background: var(--active);
    color: var(--on-active);
    font-weight: 600;
  }

  .btn.big {
    padding: 14px 28px;
    font-size: 16px;
  }

  .btn.huge {
    min-width: 200px;
    padding: 18px 34px;
    font-size: 19px;
  }

  .btn.small {
    padding: 7px 13px;
    font-size: 13px;
  }

  @media (prefers-reduced-motion: reduce) {
    .dot {
      animation: none;
    }
  }
</style>
