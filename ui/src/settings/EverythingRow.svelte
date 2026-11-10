<!--
  Estado de Everything y qué hacer (asistente → Tu equipo y Ajustes → Caché). Nyx lo usa con
  es.exe y necesita que Everything esté abierto en segundo plano. Instalarlo es siempre
  voluntario: solo con el botón.
-->
<script lang="ts">
  import Button from "$lib/controls/Button.svelte";
  import Row from "$lib/controls/Row.svelte";
  import { settings } from "./store.svelte";

  const ev = $derived(settings.setupStatus?.everything);
  const installing = $derived(settings.setupStatus?.installing_everything ?? false);
</script>

{#if ev}
  {#if installing}
    <Row
      label="Instalando Everything…"
      hint="Windows te pedirá permiso para instalarlo. Tarda menos de un minuto."
    >
      <span class="state">Instalando</span>
    </Row>
  {:else if !ev.installed}
    <Row
      label="Se usa el índice de Windows"
      hint="Funciona sin hacer nada. Con Everything (gratis, de voidtools) las búsquedas de archivos serían instantáneas en todo el disco. Es opcional."
    >
      <Button onclick={() => settings.setup("install_everything")}>Instalar</Button>
    </Row>
  {:else if !ev.running}
    <Row
      label="Everything está instalado, pero cerrado"
      hint="Nyx lo necesita abierto en segundo plano para buscar con él. Al abrirlo se queda en la bandeja y arranca solo con Windows."
    >
      <Button primary onclick={() => settings.setup("start_everything")}>Abrir Everything</Button>
    </Row>
  {:else if !ev.cli}
    <Row
      label="Falta la línea de órdenes de Everything"
      hint="Nyx habla con Everything con es.exe, un programa pequeño de voidtools que va aparte."
    >
      <Button primary onclick={() => settings.setup("install_everything")}>Instalar</Button>
    </Row>
  {:else}
    <Row
      label="Nyx usa Everything"
      hint="No tienes que hacer nada: las búsquedas de archivos van por Everything y son instantáneas."
    >
      <span class="state">Listo</span>
    </Row>
  {/if}
{/if}

<style>
  .state {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-secondary);
  }
</style>
