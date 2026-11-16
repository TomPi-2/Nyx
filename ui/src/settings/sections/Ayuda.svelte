<!-- Ajustes → Ayuda (SPEC sección 13): reiniciar Nyx, repetir el primer arranque, los registros y
  los créditos y licencias (0.9). -->
<script lang="ts">
  import { getVersion } from "@tauri-apps/api/app";
  import { invoke } from "@tauri-apps/api/core";
  import { getCurrentWindow } from "@tauri-apps/api/window";
  import Button from "$lib/controls/Button.svelte";
  import Card from "$lib/controls/Card.svelte";
  import Row from "$lib/controls/Row.svelte";
  import { CREDITS } from "../credits";
  import { settings } from "../store.svelte";

  let showCredits = $state(false);

  /** Soporte (0.9): el formulario de la web, con «Nyx» y la versión ya puestos. */
  async function contact(subject: "Bug" | "Duda") {
    const version = await getVersion().catch(() => "");
    const query = new URLSearchParams({ asunto: subject, app: "Nyx", version });
    await invoke("open_link", { url: `https://tepnyx.com/contact?${query}` });
  }

  /** El primer arranque lo guía Nyx en persona (9.10): Ajustes se cierra para dejarle sitio. */
  function repeatWelcome() {
    if (settings.startGuidedSetup()) void getCurrentWindow().close();
  }
</script>

<Card title="Si algo va mal">
  <Row
    label="Reiniciar Nyx"
    hint="Vuelve a arrancar la voz y el cerebro de Nyx. También está en el icono de la bandeja."
  >
    <Button disabled={settings.restarting} onclick={() => void settings.restartCore()}>
      {settings.restarting ? "Reiniciando…" : "Reiniciar"}
    </Button>
  </Row>
  <Row
    label="Primer arranque"
    hint="Nyx te vuelve a guiar: micrófono, su color y tamaño, los paneles, tu equipo y los datos anónimos."
  >
    <Button onclick={repeatWelcome}>Repetir</Button>
  </Row>
</Card>

<Card
  title="Contactar con soporte"
  note="Se abre el formulario de tepnyx.com. Nyx no envía nada por su cuenta: lo que escribas lo mandas tú."
>
  <Row label="Algo no funciona" hint="Cuéntanos qué pasó y, si salió, el código de error.">
    <Button onclick={() => void contact("Bug")}>Avisar de un fallo</Button>
  </Row>
  <Row label="Tengo una duda" hint="Cómo se hace algo, qué sabe hacer Nyx…">
    <Button onclick={() => void contact("Duda")}>Preguntar</Button>
  </Row>
</Card>

<Card
  title="Registros"
  note="Se quedan en tu equipo. Si algo falla, el registro de errores ayuda a saber por qué."
>
  <Row label="Registro de errores" hint="Lo que hace Nyx por dentro, con los errores.">
    <Button onclick={() => void invoke("open_folder", { kind: "logs" })}>Abrir carpeta</Button>
  </Row>
  <Row label="Registro de acciones" hint="Todo lo que Nyx ha hecho en tu equipo, día a día.">
    <Button onclick={() => void invoke("open_folder", { kind: "actions" })}>Abrir carpeta</Button>
  </Row>
</Card>

<Card
  title="Créditos y licencias"
  note="Nyx es software libre (GPL-3.0) y se apoya en el trabajo de mucha gente."
>
  <Row label="Lo que usa Nyx" hint="Quién lo ha hecho y con qué licencia.">
    <Button onclick={() => (showCredits = !showCredits)}>{showCredits ? "Ocultar" : "Ver"}</Button>
  </Row>
  {#if showCredits}
    <ul class="credits">
      {#each CREDITS as c (c.what)}
        <li>
          <div class="head">
            <span class="what">{c.what}</span>
            <button class="link" onclick={() => void invoke("open_link", { url: c.url })}
              >{c.license}</button
            >
          </div>
          <div class="meta">{c.use} · {c.who}</div>
          {#if c.note}<div class="meta">{c.note}</div>{/if}
        </li>
      {/each}
    </ul>
  {/if}
</Card>

<style>
  .credits {
    list-style: none;
    margin: 0;
    padding: 4px 0 0;
    display: grid;
    gap: 10px;
  }

  .head {
    display: flex;
    align-items: baseline;
    gap: 8px;
  }

  .what {
    flex: 1;
    font-weight: 600;
    font-size: 13.5px;
  }

  .meta {
    font-size: 12px;
    color: var(--text-secondary);
    line-height: 1.45;
  }

  .link {
    border: 0;
    padding: 0;
    background: none;
    color: var(--text-secondary);
    font: inherit;
    font-size: 12px;
    text-decoration: underline;
    text-underline-offset: 2px;
    cursor: pointer;
  }
</style>
