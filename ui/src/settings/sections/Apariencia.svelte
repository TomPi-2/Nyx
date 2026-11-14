<!-- Ajustes → Apariencia (SPEC secciones 12 y 13): Nyx y el motor de cristal. -->
<script lang="ts">
  import { emitTo } from "@tauri-apps/api/event";
  import Button from "$lib/controls/Button.svelte";
  import Card from "$lib/controls/Card.svelte";
  import Row from "$lib/controls/Row.svelte";
  import Segmented from "$lib/controls/Segmented.svelte";
  import Slider from "$lib/controls/Slider.svelte";
  import Swatches from "$lib/controls/Swatches.svelte";
  import Toggle from "$lib/controls/Toggle.svelte";
  import { edgeLevelToPx } from "$lib/glass";
  import type { GlassInfo } from "$lib/protocol";
  import Indicator from "$overlay/shape/Indicator.svelte";
  import {
    FONTS,
    NYX_COLORS,
    PANEL_TINTS,
    type FontId,
    type NyxColorId,
    type PanelTintId,
  } from "$theme/palette";
  import { onMount } from "svelte";
  import Select from "$lib/controls/Select.svelte";
  import type { MonitorSettings, ReadyIndicator } from "$lib/protocol";
  import { READY_TEST_EVENT } from "$overlay/panels/layout";
  import { monitors } from "../monitors.svelte";
  import { settings } from "../store.svelte";

  const QUALITY: { value: GlassInfo["quality"]; label: string }[] = [
    { value: "auto", label: "Auto" },
    { value: "alto", label: "Alto" },
    { value: "medio", label: "Medio" },
    { value: "bajo", label: "Bajo" },
  ];
  const QUALITY_HINT: Record<GlassInfo["quality"], string> = {
    auto: "Nyx elige el nivel: baja solo con batería, ahorro de energía, transparencias de Windows desactivadas o si la tarjeta gráfica no llega.",
    alto: "Ve lo de detrás en tiempo real, con refracción en el borde y brillo.",
    medio: "Ve lo de detrás en tiempo real, desenfocado y con tinte.",
    bajo: "Tinte gris translúcido: no mira lo de detrás y casi no gasta.",
  };
  const MOTION: { value: GlassInfo["motion"]; label: string }[] = [
    { value: "siempre", label: "Siempre" },
    { value: "interaccion", label: "Al interactuar" },
    { value: "quieto", label: "Quieto" },
  ];

  const FONT_OPTIONS = (Object.keys(FONTS) as FontId[]).map((value) => ({
    value,
    label: FONTS[value].label,
  }));
  const COLOR_OPTIONS = (Object.keys(NYX_COLORS) as NyxColorId[]).map((value) => ({
    value,
    label: NYX_COLORS[value].label,
    color: NYX_COLORS[value].hex,
  }));
  // Las muestras de tinte se ven con la versión del tema actual.
  const darkTheme = matchMedia("(prefers-color-scheme: dark)").matches;
  const TINT_OPTIONS = (Object.keys(PANEL_TINTS) as PanelTintId[]).map((value) => {
    const [r, g, b] = darkTheme ? PANEL_TINTS[value].dark : PANEL_TINTS[value].light;
    return { value, label: PANEL_TINTS[value].label, color: `rgb(${r}, ${g}, ${b})` };
  });

  const fmt = (n: number) => n.toLocaleString("es-ES", { maximumFractionDigits: 1 });

  const data = $derived(settings.data);
  const glass = $derived(data?.appearance.glass);
  // El tamaño se ve al momento en la vista previa; se guarda al soltar.
  let size = $state<number | null>(null);
  const shownSize = $derived(size ?? data?.appearance.indicator_size ?? 100);

  function setGlass(patch: Partial<GlassInfo>, debounce = false) {
    settings.set({ appearance: { glass: { ...glass!, ...patch } } }, debounce);
  }
  const READY: { value: ReadyIndicator; label: string }[] = [
    { value: "onda", label: "Onda" },
    { value: "nyx", label: "Nyx aparece" },
    { value: "nada", label: "Nada" },
  ];

  const FOLLOW: { value: MonitorSettings["follow"]; label: string }[] = [
    { value: "cursor", label: "Sigue al ratón" },
    { value: "fixed", label: "Siempre en uno" },
  ];

  function setMonitor(patch: Partial<MonitorSettings>) {
    settings.set({ appearance: { monitor: { ...data!.appearance.monitor, ...patch } } });
  }

  onMount(() => monitors.watch());
</script>

{#if data && glass}
  <Card title="Nyx">
    <div class="preview">
      <Indicator
        status="listening"
        level={0}
        size={Math.min(shownSize, 120)}
        backdrop={null}
        color={data.appearance.nyx_color}
      />
    </div>
    <Row label="Color" value={NYX_COLORS[data.appearance.nyx_color]?.label} stacked>
      <Swatches
        label="Color de Nyx"
        options={COLOR_OPTIONS}
        value={data.appearance.nyx_color}
        onchange={(nyx_color) => settings.set({ appearance: { nyx_color } })}
      />
    </Row>
    <Row label="Tamaño" value="{shownSize} px" stacked>
      <Slider
        label="Tamaño de Nyx"
        min={60}
        max={180}
        step={10}
        value={shownSize}
        oninput={(v) => (size = v)}
        onchange={(v) => {
          settings.set({ appearance: { indicator_size: v } });
          size = null;
        }}
      />
    </Row>
  </Card>

  <Card
    title="Monitor"
    note={monitors.single ? "Solo hay un monitor conectado: Nyx aparece en él." : undefined}
  >
    <div class="lockable" class:locked={monitors.single} aria-disabled={monitors.single}>
      <Row
        label="Dónde aparece Nyx"
        hint={data.appearance.monitor.follow === "cursor"
          ? "En el monitor donde tengas el ratón; si lo pasas a otro, Nyx se va con él."
          : "Siempre en el mismo monitor, tengas el ratón donde lo tengas."}
        stacked
      >
        <Segmented
          label="Dónde aparece Nyx"
          options={FOLLOW}
          value={data.appearance.monitor.follow}
          onchange={(follow) => setMonitor({ follow })}
        />
      </Row>
      {#if data.appearance.monitor.follow === "fixed"}
        <Row label="Monitor" stacked>
          <Select
            label="Monitor de Nyx"
            options={monitors.list.map((m) => ({ value: m.device, label: m.label }))}
            value={data.appearance.monitor.fixed ?? monitors.primary?.device ?? ""}
            onchange={(fixed) => setMonitor({ fixed })}
          />
        </Row>
      {/if}
      <Row
        label="Animación al cambiar de monitor"
        hint="Nyx y sus paneles se encogen en el monitor de antes y aparecen en el nuevo."
      >
        <Toggle
          label="Animación al cambiar de monitor"
          checked={data.appearance.monitor.transition}
          onchange={(transition) => setMonitor({ transition })}
        />
      </Row>
    </div>
  </Card>

  <Card title="Al estar lista">
    <Row
      label="Aviso de que Nyx está lista"
      hint={data.appearance.ready_indicator === "onda"
        ? "Al encender el PC, una onda de cristal sale de Nyx y cruza tus monitores. En partida o con el cristal en Bajo, Nyx aparece y desaparece."
        : data.appearance.ready_indicator === "nyx"
          ? "Al encender el PC, Nyx aparece un momento y se va."
          : "Sin aviso: Nyx está lista sin decir nada."}
      stacked
    >
      <Segmented
        label="Aviso de que Nyx está lista"
        options={READY}
        value={data.appearance.ready_indicator}
        onchange={(ready_indicator) => settings.set({ appearance: { ready_indicator } })}
      />
    </Row>
    <Row label="Probarlo" hint="Como al encender el PC, con lo que tengas elegido.">
      <Button
        disabled={data.appearance.ready_indicator === "nada"}
        onclick={() => void emitTo("island", READY_TEST_EVENT)}>Probar</Button
      >
    </Row>
  </Card>

  <Card title="Texto">
    <Row label="Fuente" hint="La de los paneles, el campo de texto y esta ventana." stacked>
      <Segmented
        label="Fuente"
        options={FONT_OPTIONS}
        value={data.appearance.font}
        onchange={(font) => settings.set({ appearance: { font } })}
      />
    </Row>
  </Card>

  <Card
    title="Cristal"
    note="En Alto y Medio, Nyx mira la pantalla para dibujar el cristal. Esas imágenes se quedan en la tarjeta gráfica: nunca se guardan, no salen del equipo y no las ve el modelo. Con un juego abierto no se mira nunca."
  >
    <Row
      label="Calidad"
      hint={glass.quality === "auto"
        ? QUALITY_HINT.auto
        : `${QUALITY_HINT[glass.quality]} En partida se cambia a Bajo automáticamente, sin excepción.`}
      stacked
    >
      <Segmented
        label="Calidad del cristal"
        options={QUALITY}
        value={glass.quality}
        onchange={(quality) => setGlass({ quality })}
      />
    </Row>
    <Row
      label="Tinte de los paneles"
      value={PANEL_TINTS[data.appearance.panel_tint]?.label}
      hint="El color del cristal de los paneles y de Ajustes. Cada tinte tiene su versión para el tema claro y el oscuro."
      stacked
    >
      <Swatches
        label="Tinte de los paneles"
        options={TINT_OPTIONS}
        value={data.appearance.panel_tint}
        onchange={(panel_tint) => settings.set({ appearance: { panel_tint } })}
      />
    </Row>
    <Row label="Movimiento del borde" hint="El borde ondula como un líquido." stacked>
      <Segmented
        label="Movimiento del borde"
        options={MOTION}
        value={glass.motion}
        onchange={(motion) => setGlass({ motion })}
      />
    </Row>
    <Row
      label="Amplitud del borde"
      value="{glass.edge} · {fmt(edgeLevelToPx(glass.edge))} px"
      stacked
    >
      <Slider
        label="Amplitud del borde"
        min={0}
        max={10}
        step={1}
        value={glass.edge}
        oninput={(edge) => setGlass({ edge }, true)}
      />
    </Row>
    <Row
      label="Mostrar Nyx en capturas y directos"
      hint="En Alto y Medio, los paneles no salen en capturas ni directos (la forma de Nyx sí). Activándolo, los paneles usan el nivel Bajo y salen siempre."
    >
      <Toggle
        label="Mostrar Nyx en capturas y directos"
        checked={glass.show_in_captures}
        onchange={(show_in_captures) => setGlass({ show_in_captures })}
      />
    </Row>
  </Card>
{/if}

<style>
  .preview {
    display: flex;
    justify-content: center;
    padding: 4px 0 0;
  }
</style>
