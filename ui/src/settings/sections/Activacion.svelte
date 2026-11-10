<!--
  Ajustes → Activación (SPEC secciones 4 y 13): cómo se despierta a Nyx. Solo lo que ya existe;
  estos ajustes se leen al arrancar el núcleo, así que se aplican al reiniciar Nyx.
-->
<script lang="ts">
  import Card from "$lib/controls/Card.svelte";
  import Row from "$lib/controls/Row.svelte";
  import Segmented from "$lib/controls/Segmented.svelte";
  import Slider from "$lib/controls/Slider.svelte";
  import TextField from "$lib/controls/TextField.svelte";
  import Toggle from "$lib/controls/Toggle.svelte";
  import type { NyxSettings } from "$lib/protocol";
  import { settings } from "../store.svelte";

  type Wake = NyxSettings["wake"];

  const ENGINES: { value: Wake["engine"]; label: string }[] = [
    { value: "propio", label: "Modelo de Nyx" },
    { value: "vosk", label: "Vosk" },
  ];
  const SHORTCUTS = [
    [
      "Win + Alt + H",
      "Hablar con Nyx: púlsalo una vez y te escucha hasta que termines de hablar, o mantenlo pulsado mientras hablas",
    ],
    ["Win + Alt + N", "Escribirle a Nyx"],
    ["Win + Alt + ,", "Abrir estos Ajustes"],
  ];

  const data = $derived(settings.data);
  let sensitivity = $state<number | null>(null);
  let followup = $state<number | null>(null);
  let silence = $state<number | null>(null);

  const fmt = (n: number) => n.toLocaleString("es-ES", { maximumFractionDigits: 1 });
</script>

{#if data}
  <Card title="Palabra de activación" note="Estos cambios se aplican al reiniciar Nyx.">
    <Row
      label="Despertar a Nyx con la voz"
      hint="Si lo desactivas, Nyx solo te escucha con el atajo de hablar."
    >
      <Toggle
        label="Despertar a Nyx con la voz"
        checked={data.wake.enabled}
        onchange={(enabled) => settings.set({ wake: { enabled } })}
      />
    </Row>
    <Row
      label="Sensibilidad"
      value={String(sensitivity ?? data.wake.sensitivity)}
      hint="Más alta: responde aunque hables bajo o lejos, pero puede saltar sin querer. Nyx comprueba cada activación antes de hacerte caso."
      stacked
    >
      <Slider
        label="Sensibilidad"
        min={1}
        max={10}
        step={1}
        value={sensitivity ?? data.wake.sensitivity}
        oninput={(v) => (sensitivity = v)}
        onchange={(v) => {
          settings.set({ wake: { sensitivity: v } });
          sensitivity = null;
        }}
      />
    </Row>
    <Row
      label="Detector"
      hint="El modelo de Nyx está entrenado para «Nyx» y acierta más. Vosk sirve para palabras personalizadas."
      stacked
    >
      <Segmented
        label="Detector de la palabra"
        options={ENGINES}
        value={data.wake.engine}
        onchange={(engine) => settings.set({ wake: { engine } })}
      />
    </Row>
    <Row
      label="Palabra personalizada"
      hint="Si escribes una (al menos 2 sílabas, como «oye lumen»), Nyx responderá a esa en vez de a «Nyx». Déjala vacía para usar «Nyx»."
      stacked
    >
      <TextField
        label="Palabra personalizada"
        placeholder="Nyx"
        value={data.wake.custom_word}
        onchange={(custom_word) => settings.set({ wake: { custom_word } })}
      />
    </Row>
  </Card>

  <Card title="Escucha" note="Estos cambios se aplican al reiniciar Nyx.">
    <Row
      label="Seguir hablando sin repetir «Nyx»"
      value={(followup ?? data.listen.followup_s) === 0
        ? "Desactivado"
        : `${fmt(followup ?? data.listen.followup_s)} s`}
      hint="Después de una respuesta, Nyx sigue escuchando este tiempo por si quieres pedir algo más."
      stacked
    >
      <Slider
        label="Seguir hablando sin repetir Nyx"
        min={0}
        max={15}
        step={1}
        value={followup ?? data.listen.followup_s}
        oninput={(v) => (followup = v)}
        onchange={(v) => {
          settings.set({ listen: { followup_s: v } });
          followup = null;
        }}
      />
    </Row>
    <Row
      label="Silencio para terminar"
      value="{fmt((silence ?? data.listen.silence_ms) / 1000)} s"
      hint="Cuánto silencio espera Nyx para entender que has terminado de hablar. Súbelo si te corta a mitad de frase."
      stacked
    >
      <Slider
        label="Silencio para terminar"
        min={300}
        max={1500}
        step={100}
        value={silence ?? data.listen.silence_ms}
        oninput={(v) => (silence = v)}
        onchange={(v) => {
          settings.set({ listen: { silence_ms: v } });
          silence = null;
        }}
      />
    </Row>
  </Card>

  <Card title="Atajos de teclado">
    {#each SHORTCUTS as [keys, what] (keys)}
      <Row label={keys} hint={what}>
        <span></span>
      </Row>
    {/each}
  </Card>
{/if}
