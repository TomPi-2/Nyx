<!-- Ajustes → General (SPEC sección 13): ubicación para el tiempo, arrancar con Windows y
  actualizaciones (§15). -->
<script lang="ts">
  import { onMount } from "svelte";
  import { invoke } from "@tauri-apps/api/core";
  import Toggle from "$lib/controls/Toggle.svelte";
  import Card from "$lib/controls/Card.svelte";
  import Row from "$lib/controls/Row.svelte";
  import Segmented from "$lib/controls/Segmented.svelte";
  import TextField from "$lib/controls/TextField.svelte";
  import type { NyxSettings } from "$lib/protocol";
  import { settings } from "../store.svelte";

  const data = $derived(settings.data);

  // «Arrancar con Windows»: la clave Run del usuario (la pone el instalador; autostart.rs).
  let autostart = $state<boolean | null>(null);
  onMount(() => {
    void invoke<boolean>("autostart_get").then((on) => (autostart = on));
  });
  async function setAutostart(on: boolean) {
    autostart = await invoke<boolean>("autostart_set", { on }).catch(() => !on);
  }

  type Updates = NyxSettings["updates"];
  const MODES: { value: Updates["mode"]; label: string }[] = [
    { value: "preguntar", label: "Preguntar" },
    { value: "automatico", label: "Automático" },
    { value: "avisar", label: "Solo avisar" },
  ];
  const CHANNELS: { value: Updates["channel"]; label: string }[] = [
    { value: "estable", label: "Estable" },
    { value: "beta", label: "Beta" },
  ];
  const MODE_HINT: Record<Updates["mode"], string> = {
    preguntar: "Cuando haya una versión nueva te pregunto si me reinicio (unos 10 s).",
    automatico: "Me actualizo sola cuando lleves un rato sin usar el PC, y te aviso al terminar.",
    avisar: "Solo te digo que hay una versión nueva; no me actualizo hasta que me lo pidas.",
  };
</script>

{#if data}
  <Card title="Al encender">
    <Row
      label="Arrancar con Windows"
      hint="Nyx se abre sola al encender el PC y te avisa cuando está lista."
    >
      <Toggle
        label="Arrancar con Windows"
        checked={autostart ?? false}
        disabled={autostart === null}
        onchange={(on) => void setAutostart(on)}
      />
    </Row>
  </Card>

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

  <Card
    title="Actualizaciones"
    note="Nunca me actualizo en mitad de una partida, mientras te respondo o con algo pendiente de confirmar. Antes de cambiar de versión guardo una copia de tus ajustes."
  >
    <Row label="Cuando haya una versión nueva" hint={MODE_HINT[data.updates.mode]} stacked>
      <Segmented
        label="Cuando haya una versión nueva"
        options={MODES}
        value={data.updates.mode}
        onchange={(mode) => settings.set({ updates: { mode } })}
      />
    </Row>
    <Row
      label="Canal"
      hint={data.updates.channel === "beta"
        ? "Las novedades antes que nadie, con algún fallo de más."
        : "Solo versiones probadas."}
      stacked
    >
      <Segmented
        label="Canal de actualizaciones"
        options={CHANNELS}
        value={data.updates.channel}
        onchange={(channel) => settings.set({ updates: { channel } })}
      />
    </Row>
  </Card>
{/if}
