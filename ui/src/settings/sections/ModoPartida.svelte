<!--
  Ajustes → Modo partida (SPEC secciones 9 y 13): cómo se comporta Nyx con un juego abierto,
  qué cuenta como juego y qué puede hacer mientras se juega.
-->
<script lang="ts">
  import Card from "$lib/controls/Card.svelte";
  import ListEditor from "$lib/controls/ListEditor.svelte";
  import Row from "$lib/controls/Row.svelte";
  import Segmented from "$lib/controls/Segmented.svelte";
  import Slider from "$lib/controls/Slider.svelte";
  import Toggle from "$lib/controls/Toggle.svelte";
  import type { GamePolicy, NyxSettings } from "$lib/protocol";
  import { onMount } from "svelte";
  import Select from "$lib/controls/Select.svelte";
  import { monitors } from "../monitors.svelte";
  import { settings } from "../store.svelte";
  import { toolLabel } from "../tools";

  type Game = NyxSettings["game"];

  const MODES: { value: Game["mode"]; label: string }[] = [
    { value: "off", label: "Desactivado" },
    { value: "voice", label: "Solo voz" },
    { value: "normal", label: "Normal" },
  ];
  const MODE_HINT: Record<Game["mode"], string> = {
    off: "Nyx no escucha mientras juegas (salvo con el atajo de hablar) y no aparece nada.",
    voice: "Nyx responde por voz y no aparece nada sobre el juego.",
    normal: "Nyx aparece como siempre, también sobre el juego.",
  };
  const POLICIES: { value: GamePolicy; label: string }[] = [
    { value: "allowed", label: "Sí" },
    { value: "deferred", label: "Después" },
    { value: "blocked", label: "No" },
  ];

  const data = $derived(settings.data);
  const game = $derived(data?.game);
  let unload = $state<number | null>(null);
  const shownUnload = $derived(unload ?? game?.unload_llm_after_min ?? 0);

  function setGame(patch: Partial<Game>) {
    settings.set({ game: patch });
  }

  function policyOf(name: string, fallback: GamePolicy): GamePolicy {
    return game?.policies[name] ?? fallback;
  }

  /** Volver al valor por defecto quita la entrada (así sigue los cambios futuros de Nyx). */
  function setPolicy(name: string, value: GamePolicy, fallback: GamePolicy) {
    const policies = { ...game!.policies };
    if (value === fallback) delete policies[name];
    else policies[name] = value;
    setGame({ policies });
  }

  const exe = (text: string) => {
    const name = text.trim().toLowerCase();
    if (!name) return "";
    return name.endsWith(".exe") ? name : `${name}.exe`;
  };
  /** En el desplegable, «automático» es la opción vacía. */
  const AUTO = "";

  onMount(() => monitors.watch());
</script>

{#if game}
  <Card title="Nyx en partida">
    <Row label="Comportamiento" hint={MODE_HINT[game.mode]} stacked>
      <Segmented
        label="Nyx en partida"
        options={MODES}
        value={game.mode}
        onchange={(mode) => setGame({ mode })}
      />
    </Row>
  </Card>

  <Card
    title="Monitor en partida"
    note={monitors.single
      ? "Solo hay un monitor conectado: en «Solo voz», Nyx no aparece mientras juegas."
      : undefined}
  >
    <div class="lockable" class:locked={monitors.single} aria-disabled={monitors.single}>
      <Row
        label="Si Nyx tuviera que salir en el monitor del juego"
        hint="Con «Solo voz», Nyx aparece en otro monitor para no ponerse encima del juego. Automático: el principal, o el primero sin el juego."
        stacked
      >
        <Select
          label="Monitor en partida"
          options={[
            { value: AUTO, label: "Automático" },
            ...monitors.list.map((m) => ({ value: m.device, label: m.label })),
          ]}
          value={game.alt_monitor ?? AUTO}
          onchange={(v) => setGame({ alt_monitor: v || null })}
        />
      </Row>
    </div>
  </Card>

  <Card title="Rendimiento">
    <Row label="Prioridad baja" hint="Nyx y sus procesos ceden la CPU al juego mientras juegas.">
      <Toggle
        label="Prioridad baja en partida"
        checked={game.low_priority}
        onchange={(low_priority) => setGame({ low_priority })}
      />
    </Row>
    <Row
      label="Liberar la memoria del modelo"
      value={shownUnload === 0 ? "Nunca" : `tras ${shownUnload} min`}
      hint="Tras ese tiempo de partida, el modelo deja la memoria de la tarjeta gráfica. La primera respuesta después tarda unos segundos más."
      stacked
    >
      <Slider
        label="Liberar la memoria del modelo"
        min={0}
        max={60}
        step={5}
        value={shownUnload}
        oninput={(v) => (unload = v)}
        onchange={(v) => {
          setGame({ unload_llm_after_min: v });
          unload = null;
        }}
      />
    </Row>
  </Card>

  <Card
    title="Qué cuenta como juego"
    note="Nyx detecta los juegos solo (pantalla completa, carpetas de juegos y tiendas). Aquí puedes corregirlo con el nombre del ejecutable."
  >
    <Row label="Siempre es un juego" stacked>
      <ListEditor
        label="Siempre es un juego"
        items={game.always}
        placeholder="juego.exe"
        normalize={exe}
        onchange={(always) => setGame({ always })}
      />
    </Row>
    <Row label="Nunca es un juego" stacked>
      <ListEditor
        label="Nunca es un juego"
        items={game.never}
        placeholder="programa.exe"
        normalize={exe}
        onchange={(never) => setGame({ never })}
      />
    </Row>
  </Card>

  <Card
    title="Qué puede hacer Nyx mientras juegas"
    note="«Después» la guarda y te la hace al terminar la partida. Las acciones que piden confirmación (como mandar a la papelera) se dejan siempre para después, salvo en modo Normal. Nunca se actúa dentro de un juego."
  >
    {#each settings.tools as tool (tool.name)}
      <Row label={toolLabel(tool.name)}>
        <Segmented
          compact
          label={toolLabel(tool.name)}
          options={POLICIES}
          value={policyOf(tool.name, tool.game_policy)}
          onchange={(v) => setPolicy(tool.name, v, tool.game_policy)}
        />
      </Row>
    {/each}
  </Card>
{/if}
