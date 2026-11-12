<!-- Ajustes → Respuestas (SPEC sección 13). -->
<script lang="ts">
  import Card from "$lib/controls/Card.svelte";
  import Row from "$lib/controls/Row.svelte";
  import Segmented from "$lib/controls/Segmented.svelte";
  import Toggle from "$lib/controls/Toggle.svelte";
  import type { ResponseTone } from "$lib/protocol";
  import { settings } from "../store.svelte";

  const data = $derived(settings.data);

  const TONES: { value: ResponseTone; label: string }[] = [
    { value: "cercano", label: "Cercano" },
    { value: "neutro", label: "Neutro" },
    { value: "divertido", label: "Divertido" },
  ];

  const TONE_HINT: Record<ResponseTone, string> = {
    cercano: "Breve, directo y cercano, sin rodeos ni frases de cortesía.",
    neutro: "Objetivo y directo, sin bromas ni rodeos.",
    divertido: "Ameno y con un toque de humor sutil cuando encaje, siempre breve.",
  };
</script>

{#if data}
  <Card title="Personalidad">
    <Row label="Tono al responder" hint={TONE_HINT[data.responses.tone]} stacked>
      <Segmented
        label="Tono al responder"
        options={TONES}
        value={data.responses.tone}
        onchange={(tone) => settings.set({ responses: { tone } })}
      />
    </Row>
  </Card>

  <Card title="Lo que escribes">
    <Row
      label="Responder también en voz"
      hint="Cuando le escribes a Nyx (Win+Alt+N), la respuesta sale solo en el panel. Activándolo, Nyx también la dice en voz alta."
    >
      <Toggle
        label="Responder también en voz a lo que escribes"
        checked={data.responses.speak_typed}
        onchange={(speak_typed) => settings.set({ responses: { speak_typed } })}
      />
    </Row>
  </Card>
{/if}
