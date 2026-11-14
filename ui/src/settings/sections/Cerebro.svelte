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

  /** Los modelos probados con la batería de frases, con su nombre para el usuario: el 7B base
   *  (core/nyx/setup/hardware.py, LLM_CHOICES; decisión 2026-11-11) y sus LoRA de Nyx (6.27),
   *  que se crean en Ollama a mano hasta que el instalador (0.9) los descargue. Solo aparecen
   *  los que estén instalados. */
  const SUPPORTED: { id: string; label: string }[] = [
    { id: "nyx-r2:7b", label: "Nyx · 7B (recomendado)" },
    { id: "nyx-r3:7b", label: "Nyx · 7B, ronda 3 (en prueba)" },
    { id: "qwen2.5:7b", label: "Qwen 2.5 · 7B (base, sin ajustar)" },
  ];

  const same = (a: string, b: string) => a === b || a === `${b}:latest` || b === `${a}:latest`;

  function modelOptions(installed: string[], current: string) {
    const list = SUPPORTED.filter((s) => installed.some((m) => same(m, s.id))).map((s) => ({
      value: s.id,
      label: s.label,
    }));
    // El que está en uso sale siempre, aunque no sea de la lista o no esté instalado.
    if (current && !list.some((o) => same(o.value, current))) {
      const installedNow = installed.some((m) => same(m, current));
      list.unshift({ value: current, label: installedNow ? current : `${current} (no instalado)` });
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
        hint="El que usa Nyx para entender lo que pides y responder. Solo salen los que se han probado a fondo con Nyx."
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
          hint="{shortcut.steps
            ? shortcut.steps.map(toolLabel).join(' → ')
            : toolLabel(shortcut.tool)} · {shortcut.uses === 1
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
