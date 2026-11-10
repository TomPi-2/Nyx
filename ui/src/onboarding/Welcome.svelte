<!--
  Asistente de primer arranque (SPEC sección 13). Pasos: bienvenida → modelos → micrófono →
  Nyx (color, tamaño y monitor) → tu equipo → ayudar a mejorar Nyx → listo. Todos se pueden
  saltar; si se cierra sin terminar, vuelve a salir la próxima vez que se abra Nyx. El
  micrófono solo se prueba (decisión 2026-11-10: grabar muestras no mejoraba la activación).
-->
<script lang="ts">
  import { onMount } from "svelte";
  import { getCurrentWindow } from "@tauri-apps/api/window";
  import Button from "$lib/controls/Button.svelte";
  import Card from "$lib/controls/Card.svelte";
  import Row from "$lib/controls/Row.svelte";
  import Segmented from "$lib/controls/Segmented.svelte";
  import Select from "$lib/controls/Select.svelte";
  import Slider from "$lib/controls/Slider.svelte";
  import Swatches from "$lib/controls/Swatches.svelte";
  import Toggle from "$lib/controls/Toggle.svelte";
  import { glass, glassFromSettings, glassPoke, glassShape } from "$lib/glass";
  import { POP_IN_MS, POP_OUT_MS, pop } from "$lib/motion";
  import { applyAppearance } from "$theme/apply";
  import { NYX_COLORS, type NyxColorId } from "$theme/palette";
  import Indicator from "$overlay/shape/Indicator.svelte";
  import { monitors } from "../settings/monitors.svelte";
  import { settings } from "../settings/store.svelte";
  import UsageData from "../settings/UsageData.svelte";

  const STATUS_EVERY_MS = 3000;
  type Step = "hola" | "modelos" | "micro" | "nyx" | "equipo" | "datos" | "listo";
  const STEPS: Step[] = ["hola", "modelos", "micro", "nyx", "equipo", "datos", "listo"];
  const COLORS = (Object.keys(NYX_COLORS) as NyxColorId[]).map((value) => ({
    value,
    label: NYX_COLORS[value].label,
    color: NYX_COLORS[value].hex,
  }));

  let index = $state(0);
  let closing = $state(false);
  /** Se ha descargado algo: al terminar se reinicia Nyx para usarlo. */
  let downloaded = $state(false);
  /** En el paso del micrófono: ¿se ha activado al decir «Nyx»? */
  let heard = $state(false);

  const step = $derived(STEPS[index]);
  const data = $derived(settings.data);
  const status = $derived(settings.setupStatus);
  const missing = $derived(status?.models.filter((m) => !m.present) ?? []);
  const missingMb = $derived(missing.reduce((n, m) => n + m.size_mb, 0));
  const downloads = $derived(Object.entries(settings.downloads));
  const win = getCurrentWindow();

  // Cristal y apariencia como el resto de Nyx.
  $effect(() => {
    const look = settings.data?.appearance;
    if (!look) return;
    glass.set(glassFromSettings(look.glass, look.panel_tint));
    applyAppearance(look);
  });

  // La prueba del micrófono solo mientras se está en ese paso.
  $effect(() => {
    if (step !== "micro" || !settings.connected) return;
    heard = false;
    settings.setup("mic_test_start");
    return () => settings.setup("mic_test_stop");
  });

  $effect(() => {
    if (step === "micro" && settings.nyxState === "listening") heard = true;
  });

  // Descargas terminadas sin error: hará falta reiniciar Nyx al final.
  $effect(() => {
    if (downloads.some(([, d]) => d.finished && !d.error)) downloaded = true;
  });

  function next() {
    index = Math.min(STEPS.length - 1, index + 1);
    glass.poke();
  }

  function back() {
    index = Math.max(0, index - 1);
    glass.poke();
  }

  /**
   * Se encoge como Nyx y se cierra (la ventana de verdad, al terminar la animación). `before`
   * se hace justo antes, ya sin verse.
   */
  function close(before?: () => Promise<void>, wait = POP_OUT_MS) {
    if (closing) return;
    closing = true;
    glass.follow(POP_OUT_MS + 40);
    setTimeout(async () => {
      await before?.();
      void win.destroy();
    }, wait);
  }

  function finish() {
    settings.set({ onboarding: { done: true } });
    // Se espera un poco para que el núcleo guarde «hecho» antes de reiniciarlo.
    close(downloaded ? () => settings.restartCore() : undefined, POP_OUT_MS + 400);
  }

  // En los pasos que dependen del estado (modelos, tu equipo), se vuelve a preguntar cada
  // poco: al abrir Nyx por primera vez, la caché tarda en estar lista.
  $effect(() => {
    if ((step !== "modelos" && step !== "equipo") || !settings.connected) return;
    settings.setup("status");
    const timer = setInterval(() => settings.setup("status"), STATUS_EVERY_MS);
    return () => clearInterval(timer);
  });

  const fmtMb = (mb: number) =>
    mb >= 1024
      ? `${(mb / 1024).toLocaleString("es-ES", { maximumFractionDigits: 1 })} GB`
      : `${Math.round(mb)} MB`;

  onMount(() => {
    const disconnect = settings.connect();
    const stopMonitors = monitors.watch();
    void glass.attach({ lowOpacity: 0.97 }).then(() => glass.follow(POP_IN_MS + 80));
    // Cerrar sin terminar (Alt+F4…): con animación y sin marcarlo como hecho.
    const offClose = win.onCloseRequested((event) => {
      if (closing) return;
      event.preventDefault();
      close();
    });
    return () => {
      settings.setup("mic_test_stop");
      disconnect();
      stopMonitors();
      glass.detach();
      void offClose.then((off) => off());
    };
  });
</script>

<div
  class="window"
  class:pop-in={!closing}
  class:pop-out={closing}
  use:glassShape={{ radius: 28, wobble: 0.6 }}
  use:glassPoke
>
  <header data-tauri-drag-region>
    <div class="dots" data-tauri-drag-region>
      {#each STEPS as s, i (s)}
        <span class="dot" class:on={i === index} class:done={i < index}></span>
      {/each}
    </div>
    <button class="round" aria-label="Más tarde" title="Más tarde" onclick={() => close()}>
      <svg viewBox="0 0 12 12" width="10" height="10" aria-hidden="true">
        <path
          d="M3 3l6 6M9 3l-6 6"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
        />
      </svg>
    </button>
  </header>

  {#key step}
    <main in:pop={{ duration: POP_IN_MS }}>
      {#if step === "hola"}
        <div class="hero">
          <Indicator
            status="listening"
            level={0}
            size={88}
            backdrop={null}
            color={data?.appearance.nyx_color}
          />
          <h1>Hola, soy Nyx</h1>
          <p>
            Tu asistente de voz para Windows. Funciono en tu equipo, sin cuenta y sin mandar tu voz
            a ningún sitio. En unos pasos lo dejamos listo; todos se pueden saltar y repetir luego
            desde Ajustes → Ayuda.
          </p>
        </div>
      {:else if step === "modelos"}
        <h1>Lo que necesito para oírte y pensar</h1>
        <p>Modelos que funcionan en tu equipo, sin internet una vez descargados.</p>
        {#if !status}
          <p class="muted">Comprobando…</p>
        {:else}
          <Card>
            <Row
              label="Voz y activación"
              hint={missing.length
                ? `Faltan ${missing.length} archivos (${fmtMb(missingMb)}).`
                : "Todo descargado."}
            >
              <span class="ok" class:no={missing.length > 0}
                >{missing.length ? "Falta" : "Listo"}</span
              >
            </Row>
            <Row
              label="Cerebro ({status.ollama.wanted})"
              hint={!status.ollama.running
                ? "Ollama no está en marcha. Instálalo o ábrelo y vuelve a este paso; el instalador de Nyx lo traerá más adelante."
                : status.ollama.has_wanted
                  ? "Instalado en Ollama."
                  : "Se descarga en Ollama (unos 4,7 GB)."}
            >
              <span class="ok" class:no={!status.ollama.has_wanted}>
                {status.ollama.has_wanted ? "Listo" : "Falta"}
              </span>
            </Row>
            <Row
              label="Transcripción"
              hint={status.whisper
                ? "whisper-server listo."
                : "Falta whisper-server.exe: llegará con el instalador. Mientras tanto puedes escribirle a Nyx con Win+Alt+N."}
            >
              <span class="ok" class:no={!status.whisper}>{status.whisper ? "Listo" : "Falta"}</span
              >
            </Row>
          </Card>
          {#if downloads.length}
            <div class="downloads">
              {#each downloads as [key, d] (key)}
                <div class="download">
                  <span class="name">{d.label}</span>
                  <span class="bar">
                    <span
                      style:width="{d.totalMb ? Math.min(100, (d.doneMb / d.totalMb) * 100) : 0}%"
                    ></span>
                  </span>
                  <span class="muted">
                    {d.error
                      ? "error"
                      : d.finished
                        ? "listo"
                        : `${fmtMb(d.doneMb)} / ${fmtMb(d.totalMb)}`}
                  </span>
                </div>
              {/each}
            </div>
          {/if}
          {#if missing.length || (status.ollama.running && !status.ollama.has_wanted)}
            <div class="actions">
              <Button
                primary
                disabled={status.downloading}
                onclick={() => settings.setup("download")}
              >
                {status.downloading ? "Descargando…" : "Descargar"}
              </Button>
            </div>
          {/if}
        {/if}
      {:else if step === "micro"}
        <h1>¿Me oyes? ¿Te oigo?</h1>
        <p>Habla y mira la barra. Después di «Nyx»: si te oigo, aparezco arriba.</p>
        {#if data}
          <Card>
            <Row label="Micrófono" stacked>
              <Select
                label="Micrófono"
                options={[
                  { value: "", label: "El predeterminado de Windows" },
                  ...settings.inputs.map((n) => ({ value: n, label: n })),
                ]}
                value={data.audio.input_device ?? ""}
                onchange={(v) => {
                  settings.set({ audio: { input_device: v || null } });
                  settings.setup("mic_test_start"); // se vuelve a abrir con el nuevo
                }}
              />
            </Row>
            <Row label="Nivel" stacked>
              <span class="meter"><span style:width="{settings.micLevel * 100}%"></span></span>
            </Row>
            <Row
              label={heard ? "¡Te he oído!" : "Di «Nyx»"}
              hint={heard
                ? "La activación funciona."
                : "Si no aparezco, acércate al micrófono o sube la sensibilidad en Ajustes → Activación."}
            >
              <span class="ok" class:no={!heard}>{heard ? "Listo" : "Esperando"}</span>
            </Row>
          </Card>
        {/if}
      {:else if step === "nyx"}
        <h1>Así soy yo</h1>
        <p>Elige mi color y mi tamaño. Puedes cambiarlo cuando quieras en Ajustes → Apariencia.</p>
        {#if data}
          <div class="preview">
            <Indicator
              status="listening"
              level={0}
              size={Math.min(data.appearance.indicator_size, 110)}
              backdrop={null}
              color={data.appearance.nyx_color}
            />
          </div>
          <Card>
            <Row label="Color" stacked>
              <Swatches
                label="Color de Nyx"
                options={COLORS}
                value={data.appearance.nyx_color}
                onchange={(nyx_color) => settings.set({ appearance: { nyx_color } })}
              />
            </Row>
            <Row label="Tamaño" value="{data.appearance.indicator_size} px" stacked>
              <Slider
                label="Tamaño de Nyx"
                min={60}
                max={180}
                step={10}
                value={data.appearance.indicator_size}
                onchange={(indicator_size) => settings.set({ appearance: { indicator_size } })}
              />
            </Row>
            {#if !monitors.single}
              <Row label="Monitor" stacked>
                <Segmented
                  label="Dónde aparece Nyx"
                  options={[
                    { value: "cursor", label: "Sigue al ratón" },
                    { value: "fixed", label: "Siempre en uno" },
                  ]}
                  value={data.appearance.monitor.follow}
                  onchange={(follow) =>
                    settings.set({
                      appearance: { monitor: { ...data.appearance.monitor, follow } },
                    })}
                />
              </Row>
            {/if}
          </Card>
        {/if}
      {:else if step === "equipo"}
        <h1>Conocer tu equipo</h1>
        <p>
          Miro qué aplicaciones, juegos y carpetas tienes para abrirlos al momento cuando me lo
          pidas. Se queda en tu equipo.
        </p>
        {#if status?.index}
          <Card>
            <Row
              label="{status.index.apps} aplicaciones · {status.index.games} juegos · {status.index
                .folders} carpetas"
              hint={status.index.everything
                ? "Everything está instalado: encontraré cualquier archivo al momento."
                : "Para buscar archivos uso el índice de Windows. Con Everything (gratis) sería instantáneo."}
            >
              <Button disabled={status.index.scanning} onclick={() => settings.setup("scan")}>
                {status.index.scanning ? "Escaneando…" : "Escanear"}
              </Button>
            </Row>
          </Card>
        {:else}
          <p class="muted">Arrancando…</p>
        {/if}
      {:else if step === "datos"}
        <h1>¿Me ayudas a mejorar?</h1>
        <p>
          Puedo enviar, de forma anónima, cuánto tardo y qué falla. Nunca lo que dices, tus archivos
          ni nada personal. Está desactivado salvo que lo actives.
        </p>
        {#if data}
          <Card>
            <Row label="Enviar datos de uso anónimos">
              <Toggle
                label="Enviar datos de uso anónimos"
                checked={data.privacy.usage_data}
                onchange={(usage_data) => settings.set({ privacy: { usage_data } })}
              />
            </Row>
            <UsageData />
          </Card>
        {/if}
      {:else}
        <div class="hero">
          <Indicator
            status="speaking"
            level={0.02}
            size={88}
            backdrop={null}
            color={data?.appearance.nyx_color}
          />
          <h1>Todo listo</h1>
          <ul class="tips">
            <li><b>«Nyx»</b> o <b>Win + Alt + H</b> para hablarme</li>
            <li><b>Win + Alt + N</b> para escribirme</li>
            <li><b>Win + Alt + ,</b> para abrir mis Ajustes</li>
          </ul>
          {#if downloaded}
            <p class="muted">Al terminar me reinicio para usar lo que hemos descargado.</p>
          {/if}
        </div>
      {/if}
    </main>
  {/key}

  <footer>
    {#if index > 0 && step !== "listo"}
      <Button onclick={back}>Atrás</Button>
    {/if}
    <span class="spacer"></span>
    {#if step === "hola"}
      <Button primary onclick={next}>Empezar</Button>
    {:else if step === "listo"}
      <Button primary onclick={finish}>Terminar</Button>
    {:else}
      <Button onclick={next}>Saltar</Button>
      <Button primary onclick={next}>Siguiente</Button>
    {/if}
  </footer>
</div>

<style>
  /* Margen transparente alrededor para la ondulación y la sombra (como Ajustes). */
  .window {
    position: absolute;
    inset: 14px;
    display: flex;
    flex-direction: column;
    border-radius: 28px;
    overflow: hidden;
  }

  header {
    display: flex;
    flex: none;
    align-items: center;
    justify-content: space-between;
    height: 52px;
    padding: 0 16px 0 28px;
  }

  .dots {
    display: flex;
    gap: 6px;
  }

  .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--control);
    transition:
      background 200ms ease,
      width 200ms ease;
  }

  .dot.done {
    background: var(--text-tertiary);
  }

  .dot.on {
    width: 20px;
    border-radius: 999px;
    background: var(--control-active);
  }

  .round {
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

  main {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: 14px;
    min-height: 0;
    padding: 4px 36px 8px;
    overflow-y: auto;
  }

  main::-webkit-scrollbar-track {
    margin: 4px 0 8px;
  }

  h1 {
    margin: 0;
    font-family: var(--font-display);
    font-size: 26px;
    font-weight: 600;
  }

  p {
    margin: 0;
    font-size: 14px;
    line-height: 1.5;
    color: var(--text-secondary);
  }

  .hero {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
    margin: auto 0;
    text-align: center;
  }

  .hero p {
    max-width: 52ch;
  }

  .preview {
    display: flex;
    justify-content: center;
  }

  .muted {
    font-size: 12px;
    color: var(--text-tertiary);
  }

  .ok {
    font-size: 12px;
    font-weight: 600;
    color: var(--text);
  }

  .ok.no {
    color: var(--text-tertiary);
  }

  .actions {
    display: flex;
    justify-content: flex-end;
  }

  .downloads {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .download {
    display: grid;
    grid-template-columns: 200px 1fr 120px;
    align-items: center;
    gap: 12px;
    font-size: 12px;
  }

  .download .name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .bar,
  .meter {
    position: relative;
    display: block;
    height: 6px;
    border-radius: 999px;
    background: var(--control);
    overflow: hidden;
  }

  .bar span,
  .meter span {
    position: absolute;
    inset: 0 auto 0 0;
    border-radius: 999px;
    background: var(--control-active);
    transition: width 120ms linear;
  }

  .meter {
    height: 10px;
    margin: 6px 0;
  }

  .tips {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin: 4px 0 0;
    padding: 0;
    list-style: none;
    font-size: 14px;
    color: var(--text-secondary);
  }

  .tips b {
    color: var(--text);
    font-weight: 600;
  }

  footer {
    display: flex;
    flex: none;
    gap: 8px;
    align-items: center;
    padding: 12px 24px 22px;
  }

  .spacer {
    flex: 1;
  }
</style>
