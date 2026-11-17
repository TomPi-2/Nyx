<!--
  Ajustes → Modos (8.10–8.12; docs/MODOS.md, aprobado el 2026-11-17). Qué hace cada modo y
  sus automáticos (apagados por defecto). Se entra y se sale por voz («modo trabajo», «sal del
  modo») o con «Activar» aquí. Partida no está aquí: tiene su propia sección y manda siempre.
-->
<script lang="ts">
  import Button from "$lib/controls/Button.svelte";
  import Card from "$lib/controls/Card.svelte";
  import ListEditor from "$lib/controls/ListEditor.svelte";
  import Row from "$lib/controls/Row.svelte";
  import Slider from "$lib/controls/Slider.svelte";
  import TextField from "$lib/controls/TextField.svelte";
  import Toggle from "$lib/controls/Toggle.svelte";
  import type { ModeSettings } from "$lib/protocol";
  import { settings } from "../store.svelte";

  const modes = $derived(settings.data?.modes);
  let volume = $state<number | null>(null);
  const shownVolume = $derived(volume ?? modes?.night_volume ?? 20);

  function set(patch: Partial<ModeSettings>) {
    settings.set({ modes: patch });
  }

  /** «23.30», «23:30» o «23» → «23:30»; null si no es una hora. */
  function hour(text: string): string | null {
    const m = text.trim().match(/^(\d{1,2})(?:[:.](\d{2}))?$/);
    if (!m) return null;
    const h = Number(m[1]);
    const min = Number(m[2] ?? 0);
    if (h > 23 || min > 59) return null;
    return `${String(h).padStart(2, "0")}:${String(min).padStart(2, "0")}`;
  }

  function say(phrase: string) {
    settings.say(phrase);
  }
</script>

{#if modes}
  <Card
    title={settings.mode === "trabajo" ? "Trabajo · activo" : "Trabajo"}
    note="Abre y coloca tus apps, silencia las que distraen y Nyx habla más bajo. Al salir, todo vuelve como estaba."
  >
    <Row label="Apps que abre" hint="Con dos, una a cada lado de la pantalla." stacked>
      <ListEditor
        label="Apps que abre"
        items={modes.work_apps}
        placeholder="Word"
        onchange={(work_apps) => set({ work_apps })}
      />
    </Row>
    <Row label="Apps que silencia" stacked>
      <ListEditor
        label="Apps que silencia"
        items={modes.work_mute}
        placeholder="Discord"
        onchange={(work_mute) => set({ work_mute })}
      />
    </Row>
    <Row
      label="Automático al abrir"
      hint="Pasa a Trabajo al abrir una de estas apps. Vacío: nunca."
      stacked
    >
      <ListEditor
        label="Automático al abrir"
        items={modes.work_auto_apps}
        placeholder="Visual Studio Code"
        onchange={(work_auto_apps) => set({ work_auto_apps })}
      />
    </Row>
    <div class="line">
      <Button disabled={settings.mode === "trabajo"} onclick={() => say("modo trabajo")}
        >Activar</Button
      >
    </div>
  </Card>

  <Card
    title={settings.mode === "noche" ? "Noche · activo" : "Noche"}
    note="Baja el volumen, Nyx habla más suave y te abre la luz nocturna y «no molestar» en Configuración (Windows no deja cambiarlas a una app). Las alarmas suenan como siempre."
  >
    <Row label="Volumen" value={`${shownVolume} %`} stacked>
      <Slider
        label="Volumen en modo Noche"
        min={0}
        max={100}
        step={5}
        value={shownVolume}
        oninput={(v) => (volume = v)}
        onchange={(night_volume) => {
          set({ night_volume });
          volume = null;
        }}
      />
    </Row>
    <Row label="Automático" hint="De una hora a otra cada día. Al acabar, sale sola.">
      <Toggle
        label="Noche automática"
        checked={modes.night_from !== null}
        onchange={(on) => set({ night_from: on ? "23:00" : null })}
      />
    </Row>
    {#if modes.night_from !== null}
      <Row label="Desde">
        <span class="field">
          <TextField
            label="Desde"
            maxLength={5}
            value={modes.night_from}
            onchange={(v) => {
              const h = hour(v);
              if (h) set({ night_from: h });
            }}
          />
        </span>
      </Row>
      <Row label="Hasta">
        <span class="field">
          <TextField
            label="Hasta"
            maxLength={5}
            value={modes.night_to}
            onchange={(v) => {
              const h = hour(v);
              if (h) set({ night_to: h });
            }}
          />
        </span>
      </Row>
    {/if}
    <div class="line">
      <Button disabled={settings.mode === "noche"} onclick={() => say("modo noche")}>Activar</Button
      >
    </div>
  </Card>

  <Card
    title={settings.mode === "privacidad" ? "Privacidad · activo" : "Privacidad"}
    note="Para compartir pantalla o tener gente delante: Nyx solo te oye con Win + Alt + H, las burbujas no enseñan el contenido, no usa internet y oculta las apps que elijas."
  >
    <Row label="Apps que oculta" hint="Siguen abiertas; vuelven al salir del modo." stacked>
      <ListEditor
        label="Apps que oculta"
        items={modes.privacy_hide}
        placeholder="WhatsApp"
        onchange={(privacy_hide) => set({ privacy_hide })}
      />
    </Row>
    <div class="line">
      <Button disabled={settings.mode === "privacidad"} onclick={() => say("modo privacidad")}
        >Activar</Button
      >
    </div>
  </Card>

  <Card title="Salir de un modo" note="O di «Nyx, sal del modo». Al cerrar Nyx también se sale.">
    <div class="line"><Button onclick={() => say("sal del modo")}>Salir del modo</Button></div>
  </Card>
{/if}

<style>
  .line {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  }

  .field {
    width: 96px;
  }
</style>
