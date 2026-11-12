<!--
  Ajustes → Cerebro (SPEC secciones 6 y 13): el modelo local de Ollama, el tiempo máximo de
  respuesta y los atajos aprendidos. La nube opcional aún no existe: no aparece.
-->
<script lang="ts">
  import Button from "$lib/controls/Button.svelte";
  import Card from "$lib/controls/Card.svelte";
  import Row from "$lib/controls/Row.svelte";
  import Select from "$lib/controls/Select.svelte";
  import Slider from "$lib/controls/Slider.svelte";
  import { onMount } from "svelte";
  import { settings } from "../store.svelte";
  import { toolLabel } from "../tools";

  const data = $derived(settings.data);
  const ollama = $derived(settings.setupStatus?.ollama);
  const shortcuts = $derived(settings.setupStatus?.shortcuts ?? []);
  let timeout = $state<number | null>(null);

  /** Los modelos probados con la batería de frases (core/nyx/setup/hardware.py, LLM_CHOICES).
   *  En la primera versión, uno solo: el 7B (decisión 2026-11-11). */
  const SUPPORTED = ["qwen2.5:7b"];

  function modelOptions(installed: string[], current: string) {
    const list = installed
      .filter((m) => SUPPORTED.some((s) => m === s || m === `${s}:latest`))
      .map((m) => ({ value: m, label: m }));
    if (current && !installed.some((m) => m === current || m === `${current}:latest`)) {
      list.unshift({ value: current, label: `${current} (no instalado)` });
    }
    return list;
  }
  // El estado (caché, modelos de Ollama) se pide al abrir la sección y cada poco mientras está.
  onMount(() => {
    settings.setup("status");
    const timer = setInterval(() => settings.setup("status"), 5000);
    return () => clearInterval(timer);
  });
</script>

{#if data}
  <Card
    title="Modelo"
    note={ollama && !ollama.running
      ? "Ollama no está en marcha: no se pueden ver los modelos instalados."
      : "El cambio de modelo se aplica al reiniciar Nyx."}
  >
    <div class="lockable" class:locked={!ollama?.running}>
      <Row
        label="Modelo local"
        hint="El que usa Nyx para entender lo que pides y responder. Por ahora, uno solo: el que se ha probado a fondo con Nyx."
        stacked
      >
        <Select
          label="Modelo local"
          options={modelOptions(ollama?.models ?? [], data.llm.model)}
          value={data.llm.model}
          onchange={(model) => settings.set({ llm: { model } })}
        />
      </Row>
    </div>
    <Row
      label="Tiempo máximo de respuesta"
      value="{timeout ?? data.llm.timeout_s} s"
      hint="Si el modelo tarda más, Nyx lo deja y te pide que lo repitas."
      stacked
    >
      <Slider
        label="Tiempo máximo de respuesta"
        min={4}
        max={30}
        step={1}
        value={timeout ?? data.llm.timeout_s}
        oninput={(v) => (timeout = v)}
        onchange={(v) => {
          settings.set({ llm: { timeout_s: v } });
          timeout = null;
        }}
      />
    </Row>
  </Card>

  {#if shortcuts.length}
    <Card
      title="Atajos aprendidos"
      note="Frases que Nyx ya sabe resolver sin pensar. Olvidar una hace que la vuelva a pensar la próxima vez."
    >
      <Row
        label="Todos los atajos"
        hint={shortcuts.length === 1
          ? "1 atajo aprendido."
          : `${shortcuts.length} atajos aprendidos.`}
      >
        <Button
          confirm="¿Seguro? Vuelve a pulsar"
          onclick={() => settings.setup("forget_all_shortcuts")}>Olvidar todos</Button
        >
      </Row>
      {#each shortcuts as shortcut (shortcut.phrase)}
        <Row
          label="«{shortcut.phrase}»"
          hint="{toolLabel(shortcut.tool)} · {shortcut.uses === 1
            ? 'usado 1 vez'
            : `usado ${shortcut.uses} veces`}"
        >
          <Button onclick={() => settings.setup("forget_shortcut", shortcut.phrase)}>Olvidar</Button
          >
        </Row>
      {/each}
    </Card>
  {:else}
    <!-- Sin atajos no hay tarjeta: solo el título y la explicación. -->
    <Card
      title="Atajos aprendidos"
      note="Nyx aún no ha aprendido ningún atajo. Los aprende cuando resuelve una acción sencilla."
    />
  {/if}
{/if}
