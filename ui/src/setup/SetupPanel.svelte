<!--
  Panel del primer arranque guiado por Nyx (9.10; prototipo docs/prototipos/instalador.html):
  va debajo de Nyx en la ventana de paneles. Arriba, lo que dice Nyx (se escribe mientras
  suena); en medio, lo de cada paso; abajo, los puntos y los botones. Cada toque va al núcleo
  (setup/flow.py), que lo aplica por el camino de Ajustes y hace que Nyx lo comente. También
  es el panel suelto de «Nyx, quiero cambiarte el color» (9.11): entonces solo lleva «Listo».
-->
<script lang="ts">
  import { glassPoke, glassShape } from "$lib/glass";
  import NamedSwatches from "$lib/controls/NamedSwatches.svelte";
  import Slider from "$lib/controls/Slider.svelte";
  import type { SetupFlowAction, SetupFlowState } from "$lib/protocol";
  import { NYX_COLORS, PANEL_TINTS, type NyxColorId, type PanelTintId } from "$theme/palette";
  import UsageData from "../settings/UsageData.svelte";
  import { PANEL_RADIUS } from "../overlay/panels/layout";
  import MicStep from "./MicStep.svelte";
  import ScanStep from "./ScanStep.svelte";

  interface Props {
    flow: SetupFlowState;
    /** Nyx está hablando (el texto se escribe mientras; si se calla, se completa). */
    speaking: boolean;
    micLevel: number;
    /** Solo el texto (despedida): sin cuerpo ni botones. */
    closing?: boolean;
    send: (action: SetupFlowAction, value?: string | number | boolean | null) => void;
  }
  let { flow, speaking, micLevel, closing = false, send }: Props = $props();

  /** Lo que tarda en escribirse cada letra: más o menos al ritmo de la voz. */
  const CHAR_MS = 45;
  let shown = $state("");
  let typing: ReturnType<typeof setInterval> | undefined;
  $effect(() => {
    const text = flow.say;
    clearInterval(typing);
    let n = 0;
    shown = "";
    typing = setInterval(() => {
      n += 1;
      shown = text.slice(0, n);
      if (n >= text.length) clearInterval(typing);
    }, CHAR_MS);
    return () => clearInterval(typing);
  });
  // Si la voz acaba antes que el texto, el texto se completa.
  let wasSpeaking = false;
  $effect(() => {
    if (wasSpeaking && !speaking && shown !== flow.say) {
      clearInterval(typing);
      shown = flow.say;
    }
    wasSpeaking = speaking;
  });

  const dark = matchMedia("(prefers-color-scheme: dark)").matches;
  const COLORS = (Object.keys(NYX_COLORS) as NyxColorId[]).map((value) => ({
    value,
    label: NYX_COLORS[value].label,
    color: NYX_COLORS[value].hex,
  }));
  const TINTS = (Object.keys(PANEL_TINTS) as PanelTintId[]).map((value) => {
    const [r, g, b] = dark ? PANEL_TINTS[value].dark : PANEL_TINTS[value].light;
    return { value, label: PANEL_TINTS[value].label, color: `rgb(${r}, ${g}, ${b})` };
  });

  const single = $derived(flow.mode !== "first_run");
  const last = $derived(flow.index === flow.total - 1);
  // El tamaño se ve al momento mientras se arrastra (sin que Nyx hable); al soltar, lo comenta.
  let size = $state<number | null>(null);
  const shownSize = $derived(size ?? flow.size);
</script>

<div class="panel" use:glassShape={{ radius: PANEL_RADIUS }} use:glassPoke>
  <p class="say">
    {shown}{#if speaking && shown !== flow.say}<span class="caret"></span>{/if}
  </p>

  {#if !closing}
    {#if flow.step === "welcome" && !single}
      <p class="note">Contéstame hablando, sin decir «Nyx»: «empezar» o «saltar».</p>
    {:else if flow.step === "mic"}
      <MicStep
        mics={flow.mics}
        mic={flow.mic}
        speakers={flow.speakers ?? []}
        speaker={flow.speaker ?? null}
        level={micLevel}
        heard={flow.heard}
        woke={flow.woke}
        onpick={(i) => send("mic", i)}
        onspeaker={(i) => send("speaker", i)}
      />
    {:else if flow.step === "color"}
      <NamedSwatches
        label="Color de Nyx"
        options={COLORS}
        value={flow.color as NyxColorId}
        onchange={(v) => send("pick", v)}
      />
    {:else if flow.step === "size"}
      <div class="size">
        <Slider
          label="Tamaño de Nyx"
          min={60}
          max={180}
          step={10}
          value={shownSize}
          bubble={(v) => `${v} px`}
          oninput={(v) => {
            size = v;
            send("size_live", v);
          }}
          onchange={(v) => {
            send("size", v);
            size = null;
          }}
        />
        <div class="scale"><span>Más pequeña</span><span>Más grande</span></div>
      </div>
      <p class="note">Tamaño: <b>{shownSize} px</b> · el de siempre es 100</p>
    {:else if flow.step === "tint"}
      <NamedSwatches
        label="Color de los paneles"
        options={TINTS}
        columns={4}
        value={flow.tint as PanelTintId}
        onchange={(v) => send("pick", v)}
      />
      <p class="note">La letra, el monitor y el cristal, en Ajustes → Apariencia.</p>
    {:else if flow.step === "scan"}
      <ScanStep
        scan={flow.scan}
        everything={flow.everything}
        installing={flow.installing_everything}
        oninstall={() => send("install_everything")}
      />
    {:else if flow.step === "data"}
      <UsageData />
      <div class="choice">
        <button class:primary={flow.usage === false} onclick={() => send("data", false)}
          >No, gracias</button
        >
        <button class:primary={flow.usage === true} onclick={() => send("data", true)}
          >Sí, ayudo</button
        >
      </div>
    {/if}

    <div class="foot">
      {#if single}
        <span class="spacer"></span>
        <button class="primary" onclick={() => send("done")}>Listo</button>
      {:else if flow.step === "welcome"}
        <button class="link" onclick={() => send("skip")}>Saltar</button>
        <span class="spacer"></span>
        <button class="primary" onclick={() => send("next")}>Empezar</button>
      {:else}
        <div class="dots" aria-hidden="true">
          {#each Array.from({ length: flow.total }, (_, i) => i) as i (i)}
            <i class:on={i === flow.index}></i>
          {/each}
        </div>
        <span class="spacer"></span>
        <button onclick={() => send("back")}>Atrás</button>
        {#if last}
          <button class="primary" disabled={flow.usage === null} onclick={() => send("done")}
            >Terminar</button
          >
        {:else}
          <button class="primary" onclick={() => send("next")}>Siguiente</button>
        {/if}
      {/if}
    </div>
  {/if}
</div>

<style>
  .panel {
    display: grid;
    gap: 14px;
    width: 420px;
    padding: 18px 20px 16px;
    border-radius: 26px;
  }

  .say {
    margin: 0;
    min-height: 2.9em;
    font-size: 15px;
    line-height: 1.45;
    transition: opacity 150ms ease;
  }

  .caret {
    display: inline-block;
    width: 2px;
    height: 1em;
    margin-left: 1px;
    vertical-align: -2px;
    background: var(--text-secondary);
    animation: caret 0.8s steps(1) infinite;
  }

  @keyframes caret {
    50% {
      opacity: 0;
    }
  }

  .note {
    margin: 0;
    font-size: 12px;
    color: var(--text-secondary);
  }

  .size {
    display: grid;
    gap: 2px;
    padding-top: 12px;
  }

  .scale {
    display: flex;
    justify-content: space-between;
    font-size: 11.5px;
    color: var(--text-tertiary);
  }

  .foot,
  .choice {
    display: flex;
    gap: 8px;
    align-items: center;
  }

  .choice {
    justify-content: flex-end;
  }

  .spacer {
    flex: 1;
  }

  button {
    flex: none;
    padding: 9px 18px;
    border: none;
    border-radius: 999px;
    background: var(--control);
    color: var(--text);
    font: inherit;
    font-size: 14px;
    white-space: nowrap;
    cursor: pointer;
    transition:
      transform 150ms ease,
      opacity 200ms ease;
  }

  button:active {
    transform: scale(0.96);
  }

  button:disabled {
    opacity: 0.4;
    cursor: default;
  }

  button.primary {
    background: var(--control-active);
    color: var(--text-on-active);
    font-weight: 600;
  }

  button.link {
    padding: 9px 6px;
    background: transparent;
    color: var(--text-secondary);
  }

  .dots {
    display: flex;
    gap: 6px;
    align-items: center;
  }

  .dots i {
    width: 6px;
    height: 6px;
    border-radius: 999px;
    background: var(--control);
    transition: width 300ms ease;
  }

  .dots i.on {
    width: 18px;
    background: var(--text);
  }

  @media (prefers-reduced-motion: reduce) {
    .caret {
      animation: none;
    }
  }
</style>
