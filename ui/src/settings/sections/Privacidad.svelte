<!--
  Ajustes → Privacidad (SPEC sección 8): qué sale del equipo, los datos de uso anónimos
  (desactivados por defecto) y borrar lo que Nyx ha guardado de tu voz (a la papelera).
-->
<script lang="ts">
  import Button from "$lib/controls/Button.svelte";
  import Card from "$lib/controls/Card.svelte";
  import Row from "$lib/controls/Row.svelte";
  import Toggle from "$lib/controls/Toggle.svelte";
  import UsageData from "../UsageData.svelte";
  import { settings } from "../store.svelte";

  const data = $derived(settings.data);
  const status = $derived(settings.setupStatus);
  let showDetail = $state(false);
</script>

<Card title="Qué sale de tu equipo">
  <p class="text">
    Nyx funciona en tu equipo: lo que dices y escribes, tus archivos y lo que hay en tu pantalla no
    salen de él. Solo se conecta a internet para lo que pides (abrir una página, buscar algo,
    descargar los modelos) y, si lo activas abajo, para los datos de uso anónimos.
  </p>
</Card>

{#if data}
  <Card title="Buscar en internet">
    <Row
      label="Buscar lo que no sé"
      hint="Busco en Wikipedia cuando me lo pides o no sé algo. Solo sale lo que se busca, nunca datos de tu equipo, y te digo de dónde lo he sacado."
    >
      <Toggle
        label="Buscar lo que no sé"
        checked={data.web.enabled}
        onchange={(enabled) => settings.set({ web: { enabled } })}
      />
    </Row>
  </Card>

  <Card title="Ayudar a mejorar Nyx">
    <Row
      label="Enviar datos de uso anónimos"
      hint="Cuánto tarda Nyx, qué herramientas se usan y qué falla, sin nada personal. Aún no se envía nada: se guarda tu elección para cuando llegue."
    >
      <Toggle
        label="Enviar datos de uso anónimos"
        checked={data.privacy.usage_data}
        onchange={(usage_data) => settings.set({ privacy: { usage_data } })}
      />
    </Row>
    <Row label="Qué se enviaría exactamente" stacked>
      <Button onclick={() => (showDetail = !showDetail)}>
        {showDetail ? "Ocultar" : "Ver qué se envía"}
      </Button>
    </Row>
    {#if showDetail}
      <UsageData />
    {/if}
  </Card>
{/if}

<Card
  title="Tu voz"
  note="Va a la papelera de Windows: si te arrepientes, puedes recuperarlo desde allí."
>
  <Row
    label="Grabaciones de calibración"
    hint={status?.samples
      ? `${status.samples} grabaciones de «Nyx» que hiciste para ajustar la activación.`
      : "No hay grabaciones guardadas."}
  >
    <Button
      disabled={!status?.samples}
      confirm="¿Seguro? Vuelve a pulsar"
      onclick={() => settings.setup("clear_samples")}
    >
      A la papelera
    </Button>
  </Row>
  <Row
    label="Registro de activaciones"
    hint={status?.activations
      ? `Cuándo se ha activado Nyx (${status.activations} días), sin audio salvo que guardes los sonidos en Activación. Sirve para que se active menos por error.`
      : "No hay registro de activaciones."}
  >
    <Button
      disabled={!status?.activations}
      confirm="¿Seguro? Vuelve a pulsar"
      onclick={() => settings.setup("clear_activations")}
    >
      A la papelera
    </Button>
  </Row>
</Card>

<style>
  .text {
    margin: 10px 0;
    font-size: 13px;
    line-height: 1.5;
    color: var(--text-secondary);
  }
</style>
