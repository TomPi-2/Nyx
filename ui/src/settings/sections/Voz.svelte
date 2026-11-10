<!--
  Ajustes → Voz (SPEC secciones 5 y 13): la voz de Nyx y los dispositivos de audio. Se leen al
  arrancar el núcleo, así que se aplican al reiniciar Nyx.
-->
<script lang="ts">
  import Card from "$lib/controls/Card.svelte";
  import Row from "$lib/controls/Row.svelte";
  import Segmented from "$lib/controls/Segmented.svelte";
  import Select from "$lib/controls/Select.svelte";
  import Slider from "$lib/controls/Slider.svelte";
  import Toggle from "$lib/controls/Toggle.svelte";
  import { settings } from "../store.svelte";

  /** En el desplegable, el predeterminado de Windows es la opción vacía. */
  const DEFAULT = "";

  const data = $derived(settings.data);
  let speed = $state<number | null>(null);

  const fmt = (n: number) => n.toLocaleString("es-ES", { maximumFractionDigits: 2 });

  function deviceOptions(names: string[], current: string | null) {
    const list = [{ value: DEFAULT, label: "El predeterminado de Windows" }];
    // Si el elegido no está conectado ahora, se sigue viendo (y se avisa).
    if (current && !names.includes(current)) {
      list.push({ value: current, label: `${current} (no conectado)` });
    }
    return [...list, ...names.map((n) => ({ value: n, label: n }))];
  }
</script>

{#if data}
  <Card title="Voz de Nyx" note="Estos cambios se aplican al reiniciar Nyx.">
    <Row label="Respuestas habladas" hint="Si lo desactivas, Nyx solo responde en los paneles.">
      <Toggle
        label="Respuestas habladas"
        checked={data.tts.enabled}
        onchange={(enabled) => settings.set({ tts: { enabled } })}
      />
    </Row>
    {#if settings.voices.length}
      <Row label="Voz" stacked>
        <Segmented
          label="Voz"
          options={settings.voices.map((v) => ({ value: v.id, label: v.label }))}
          value={data.tts.voice}
          onchange={(voice) => settings.set({ tts: { voice } })}
        />
      </Row>
    {/if}
    <Row label="Velocidad" value="{fmt(speed ?? data.tts.speed)}×" stacked>
      <Slider
        label="Velocidad de la voz"
        min={0.5}
        max={2}
        step={0.05}
        value={speed ?? data.tts.speed}
        oninput={(v) => (speed = v)}
        onchange={(v) => {
          settings.set({ tts: { speed: v } });
          speed = null;
        }}
      />
    </Row>
  </Card>

  <Card
    title="Dispositivos"
    note="Si el dispositivo elegido se desconecta, Nyx usa el predeterminado de Windows. Estos cambios se aplican al reiniciar Nyx."
  >
    <Row label="Micrófono" stacked>
      <Select
        label="Micrófono"
        options={deviceOptions(settings.inputs, data.audio.input_device)}
        value={data.audio.input_device ?? DEFAULT}
        onchange={(v) => settings.set({ audio: { input_device: v || null } })}
      />
    </Row>
    <Row label="Altavoz o auriculares" stacked>
      <Select
        label="Altavoz o auriculares"
        options={deviceOptions(settings.outputs, data.audio.output_device)}
        value={data.audio.output_device ?? DEFAULT}
        onchange={(v) => settings.set({ audio: { output_device: v || null } })}
      />
    </Row>
  </Card>
{/if}
