<!-- Ajustes → Respuestas (SPEC sección 13). Solo lo que ya existe; el resto llega con 5c‑2. -->
<script lang="ts">
  import Card from "$lib/controls/Card.svelte";
  import Row from "$lib/controls/Row.svelte";
  import Toggle from "$lib/controls/Toggle.svelte";
  import { settings } from "../store.svelte";

  const data = $derived(settings.data);
</script>

{#if data}
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
