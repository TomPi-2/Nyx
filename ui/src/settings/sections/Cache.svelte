<!--
  Ajustes → Caché (SPEC secciones 10 y 13): lo que Nyx sabe de tu equipo (aplicaciones,
  juegos y carpetas) para encontrarlo al momento, y volver a escanearlo.
-->
<script lang="ts">
  import Button from "$lib/controls/Button.svelte";
  import Card from "$lib/controls/Card.svelte";
  import Row from "$lib/controls/Row.svelte";
  import EverythingRow from "../EverythingRow.svelte";
  import { onMount } from "svelte";
  import { settings } from "../store.svelte";

  const index = $derived(settings.setupStatus?.index);

  /** «hace 5 min», «hace 3 h», «el 12 de noviembre». */
  function when(seconds: number | null): string {
    if (seconds === null) return "nunca";
    const ago = Date.now() / 1000 - seconds;
    if (ago < 90) return "hace un momento";
    if (ago < 3600) return `hace ${Math.round(ago / 60)} min`;
    if (ago < 86400) return `hace ${Math.round(ago / 3600)} h`;
    return new Date(seconds * 1000).toLocaleDateString("es-ES", { day: "numeric", month: "long" });
  }
  // El estado (caché, modelos de Ollama) se pide al abrir la sección y cada poco mientras está.
  onMount(() => {
    settings.setup("status");
    const timer = setInterval(() => settings.setup("status"), 5000);
    return () => clearInterval(timer);
  });
</script>

<Card
  title="Aplicaciones, juegos y carpetas"
  note="Nyx lo vuelve a escanear solo cada cierto tiempo y cuando instalas algo. Hazlo a mano si acabas de instalar algo y no lo encuentra."
>
  {#if index}
    <Row
      label="{index.total} entradas"
      hint="{index.apps} aplicaciones · {index.games} juegos · {index.folders} carpetas · último escaneo {when(
        index.last_scan,
      )}"
    >
      <Button disabled={index.scanning} onclick={() => settings.setup("scan")}>
        {index.scanning ? "Escaneando…" : "Volver a escanear"}
      </Button>
    </Row>
    <EverythingRow />
  {:else}
    <Row label="Nyx está arrancando" hint="La caché estará lista en unos segundos.">
      <span></span>
    </Row>
  {/if}
</Card>
