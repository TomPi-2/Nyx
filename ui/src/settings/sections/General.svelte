<!-- Ajustes → General (SPEC sección 13): ubicación para el tiempo. -->
<script lang="ts">
  import Card from "$lib/controls/Card.svelte";
  import Row from "$lib/controls/Row.svelte";
  import TextField from "$lib/controls/TextField.svelte";
  import { settings } from "../store.svelte";

  const data = $derived(settings.data);
</script>

{#if data}
  <Card title="El tiempo">
    <Row
      label="Tu ciudad"
      hint="Para responderte cuando preguntes por el tiempo («¿va a llover mañana?», «¿qué temperatura hace?»). Se consulta en Open‑Meteo sin mandar nada más de tu equipo."
      stacked
    >
      <TextField
        label="Tu ciudad"
        placeholder="Ej.: Madrid, Valencia, Sevilla…"
        value={data.general.city}
        maxLength={100}
        onchange={(city) => settings.set({ general: { city } })}
      />
    </Row>
  </Card>
{/if}
