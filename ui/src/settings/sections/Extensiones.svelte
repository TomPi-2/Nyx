<!--
  Ajustes → Extensiones (7.11; prototipo aprobado docs/prototipos/extensiones.html). Cada
  extensión dice qué puede hacer en lenguaje normal, como los permisos de un móvil. Las de
  Tepnyx van firmadas; sin firma, solo con el modo desarrollador y con «Sin revisar».
  Desinstalar manda la carpeta a la papelera. Todo se aplica al momento (en partida, al
  terminar). El núcleo: core/nyx/ext/service.py.
-->
<script lang="ts">
  import { open } from "@tauri-apps/plugin-dialog";
  import Button from "$lib/controls/Button.svelte";
  import Card from "$lib/controls/Card.svelte";
  import Row from "$lib/controls/Row.svelte";
  import Toggle from "$lib/controls/Toggle.svelte";
  import type { ExtStatus } from "$lib/protocol";
  import { settings } from "../store.svelte";

  const ext = $derived(settings.extensions);
  let openId = $state<string | null>(null);
  /** Paquete elegido: se enseña qué trae antes de instalarlo. */
  let choosing = $state(false);

  /** Los permisos en lenguaje normal: [qué puede hacer, matiz]. */
  function describe(p: string): [string, string] {
    const [kind, ...rest] = p.split(":");
    const sub = rest[0] ?? "";
    const target = rest.slice(1).join(":");
    switch (kind) {
      case "net": {
        const where = rest.join(":");
        return [
          where.startsWith("localhost") || where.startsWith("127.")
            ? "Conectarse a un programa de este PC"
            : `Conectarse a ${rest[0]}`,
          where,
        ];
      }
      case "files":
        return sub === "write"
          ? [`Guardar archivos en tu carpeta ${target}`, "lo que sustituya va a la papelera"]
          : [`Leer archivos de tu carpeta ${target}`, ""];
      case "apps":
        return sub === "launch"
          ? ["Abrir programas", ""]
          : [`Usar botones y atajos de ${target}`, "con aviso para deshacer"];
      case "audio":
        return ["Cambiar el volumen", ""];
      case "media":
        return ["Pausar y cambiar la música", ""];
      case "clipboard":
        return sub === "read"
          ? ["Leer lo que tienes copiado", "solo cuando se lo pidas"]
          : ["Copiar texto", ""];
      case "notify":
        return ["Avisarte", ""];
      case "ui":
        return ["Enseñarte paneles", ""];
      case "secrets":
        return [
          "Guardar claves en el Administrador de credenciales de Windows",
          "nadie más las ve",
        ];
      case "llm":
        return ["Usar el cerebro de Nyx", "con un límite"];
      case "messages":
        return [`Mandar mensajes por ${sub}`, "siempre te pregunta antes"];
      default:
        return [p, ""];
    }
  }

  async function choose() {
    const path = await open({
      multiple: false,
      directory: false,
      filters: [{ name: "Extensión de Nyx", extensions: ["nyxext"] }],
    });
    if (typeof path === "string") {
      choosing = true;
      settings.ext("inspect", undefined, path);
    }
  }

  function install() {
    const pkg = ext?.inspect;
    if (pkg) settings.ext("install", undefined, pkg.path);
    choosing = false;
  }

  function letter(e: { name: string }) {
    return e.name.trim().charAt(0).toUpperCase() || "?";
  }

  function toggle(e: ExtStatus, on: boolean) {
    settings.ext(on ? "enable" : "disable", e.id);
  }
</script>

{#if ext}
  <Card
    title="Instaladas"
    note="Las extensiones piden cosas a Nyx y Nyx decide: nunca tocan un juego ni se saltan lo que te pregunta antes de hacer."
  >
    {#if ext.items.length === 0}
      <p class="empty">Aún no tienes ninguna.</p>
    {/if}
    {#each ext.items as e (e.id)}
      <div class="ext">
        <button class="head" onclick={() => (openId = openId === e.id ? null : e.id)}>
          <span class="icon" aria-hidden="true">{letter(e)}</span>
          <span class="grow">
            <span class="name">
              {e.name}
              {#if e.dev}<span class="badge strong">Sin revisar</span>{/if}
              {#if e.pending_permissions.length}<span class="badge">Actualización</span>{/if}
              {#if e.problems.length}<span class="badge strong">Con problemas</span>{/if}
            </span>
            <span class="hint"
              >{e.author} · {e.version}{e.description ? ` · ${e.description}` : ""}</span
            >
          </span>
        </button>
        <Toggle label={`Activar ${e.name}`} checked={e.enabled} onchange={(on) => toggle(e, on)} />
      </div>
      {#if openId === e.id}
        <div class="more">
          {#each e.problems as problem (problem)}<p class="problem">{problem}</p>{/each}
          <p class="hint">Puede:</p>
          <ul class="perms">
            {#each e.permissions as p (p)}
              {@const [what, why] = describe(p)}
              <li class:new={e.pending_permissions.includes(p)}>
                {what}{#if why}<span class="why"> · {why}</span>{/if}
              </li>
            {:else}
              <li>No pide nada: solo contenido, no ejecuta código.</li>
            {/each}
          </ul>
          {#if e.pending_permissions.length}
            <p class="problem">
              Su actualización pide además:
              <b>{e.pending_permissions.map((p) => describe(p)[0].toLowerCase()).join(", ")}</b>.
              Mientras no lo aceptes, sigue la versión que tienes.
            </p>
            <div class="line">
              <Button primary onclick={() => settings.ext("accept", e.id)}
                >Aceptar y actualizar</Button
              >
            </div>
          {/if}
          <div class="line">
            <Button
              confirm={`¿Desinstalar ${e.name}? Pulsa otra vez`}
              onclick={() => settings.ext("uninstall", e.id)}>Desinstalar</Button
            >
          </div>
        </div>
      {/if}
    {/each}
  </Card>

  <Card title="Añadir">
    <Row label="Desde un archivo" hint="Un .nyxext que te hayas descargado.">
      <Button onclick={() => void choose()}>Elegir archivo…</Button>
    </Row>
    {#if choosing && ext.inspect}
      {@const pkg = ext.inspect}
      <div class="sheet">
        <div class="head static">
          <span class="icon" aria-hidden="true">{letter(pkg)}</span>
          <span class="grow">
            <span class="name">{pkg.name}</span>
            <span class="hint"
              >{pkg.author} · {pkg.version} · {pkg.signed
                ? "Firmada por Tepnyx"
                : "Sin revisar"}</span
            >
          </span>
        </div>
        {#if pkg.description}<p class="hint">{pkg.description}</p>{/if}
        {#if pkg.installable}
          <p class="hint">Podrá:</p>
          <ul class="perms">
            {#each pkg.permissions as p (p)}
              {@const [what, why] = describe(p)}
              <li>
                {what}{#if why}<span class="why"> · {why}</span>{/if}
              </li>
            {:else}
              <li>No pide nada: solo contenido, no ejecuta código.</li>
            {/each}
          </ul>
          <div class="line">
            <Button onclick={() => (choosing = false)}>Cancelar</Button>
            <Button primary onclick={install}
              >{pkg.installed_version ? "Actualizar" : "Instalar"}</Button
            >
          </div>
        {:else}
          <p class="problem">
            No la ha revisado Tepnyx. Solo se puede instalar con el modo desarrollador (más abajo).
          </p>
          <div class="line">
            <Button onclick={() => (choosing = false)}>Entendido</Button>
          </div>
        {/if}
      </div>
    {/if}
    {#if ext.error}<p class="problem">{ext.error}</p>{/if}
    <Row label="Tienda de extensiones" hint="En tepnyx.com, con Nyx 1.0.">
      <span class="badge">Pronto</span>
    </Row>
  </Card>

  <Card
    title="Para desarrolladores"
    note="Una vez al día Nyx mira si Tepnyx ha retirado alguna extensión (solo si tienes alguna firmada)."
  >
    <Row
      label="Modo desarrollador"
      hint="Instalar extensiones sin firmar para probarlas. Salen como «Sin revisar»."
    >
      <Toggle
        label="Modo desarrollador"
        checked={settings.data?.extensions.dev_mode ?? ext.devMode}
        onchange={(dev_mode) => settings.set({ extensions: { dev_mode } })}
      />
    </Row>
  </Card>
{/if}

<style>
  .empty {
    margin: 0;
    font-size: 13px;
    color: var(--text-secondary);
  }

  .ext {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .head {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: center;
    gap: 12px;
    border: 0;
    padding: 6px 0;
    background: none;
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
  }

  .head.static {
    cursor: default;
  }

  .icon {
    width: 36px;
    height: 36px;
    flex: none;
    display: grid;
    place-items: center;
    border-radius: 12px;
    background: var(--control);
    font-weight: 600;
  }

  .grow {
    flex: 1;
    min-width: 0;
    display: grid;
    gap: 2px;
  }

  .name {
    font-weight: 600;
    font-size: 13.5px;
    display: flex;
    gap: 6px;
    align-items: center;
    flex-wrap: wrap;
  }

  .hint {
    margin: 0;
    font-size: 12px;
    color: var(--text-secondary);
  }

  .badge {
    padding: 2px 8px;
    border-radius: 999px;
    background: var(--control);
    font-size: 11px;
    font-weight: 500;
    color: var(--text-secondary);
  }

  .badge.strong {
    background: var(--control-active);
    color: var(--text-on-active);
  }

  .more,
  .sheet {
    display: grid;
    gap: 8px;
    padding: 4px 0 10px 48px;
  }

  .sheet {
    padding: 12px 14px;
    border-radius: 16px;
    background: var(--glass-raised);
  }

  .perms {
    margin: 0;
    padding-left: 18px;
    display: grid;
    gap: 4px;
    font-size: 13px;
  }

  .perms li.new {
    font-weight: 600;
  }

  .why {
    color: var(--text-secondary);
    font-size: 12px;
  }

  .problem {
    margin: 0;
    font-size: 12.5px;
    color: var(--text);
    padding: 8px 12px;
    border-radius: 12px;
    background: var(--glass-raised);
  }

  .line {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
  }
</style>
