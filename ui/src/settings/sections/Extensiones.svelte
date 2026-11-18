<!--
  Ajustes → Extensiones, como una tienda (prototipo aprobado el 2026-11-15,
  docs/prototipos/tienda-extensiones.html). Tres pestañas:
  - Tienda: buscar, categorías, destacadas y una ficha por extensión (qué hace, qué decirle,
    qué necesita, cómo se prepara —lo que hace Nyx, marcado—, qué podrá hacer y novedades). En la
    beta se ven las primeras, pero se instalan con Nyx 1.0.0 (decisión 2026-11-15).
  - Instaladas: activar, sus ajustes, actualizar y desinstalar (a la papelera), e instalar un
    .nyxext. Cada permiso, en lenguaje normal, como los de un móvil.
  - Desarrolladores: modo desarrollador («Sin revisar»), cargar una carpeta, la guía, y que toda
    extensión publicada la revisa Tepnyx (y 10 € de saldo a quien publique; 2026-11-18).
  El núcleo: core/nyx/ext/service.py.
-->
<script lang="ts">
  import { invoke } from "@tauri-apps/api/core";
  import { open } from "@tauri-apps/plugin-dialog";
  import Button from "$lib/controls/Button.svelte";
  import Card from "$lib/controls/Card.svelte";
  import Row from "$lib/controls/Row.svelte";
  import Segmented from "$lib/controls/Segmented.svelte";
  import TextField from "$lib/controls/TextField.svelte";
  import Toggle from "$lib/controls/Toggle.svelte";
  import type { ExtStatus } from "$lib/protocol";
  import { CATEGORIES, STORE, type StoreEntry } from "../catalog";
  import { settings } from "../store.svelte";

  type Tab = "tienda" | "instaladas" | "dev";
  const TABS: { value: Tab; label: string }[] = [
    { value: "tienda", label: "Tienda" },
    { value: "instaladas", label: "Instaladas" },
    { value: "dev", label: "Desarrolladores" },
  ];
  const STORE_URL = "https://tepnyx.com/nyx/extensiones";

  const ext = $derived(settings.extensions);
  let tab = $state<Tab>("tienda");
  let openId = $state<string | null>(null);
  /** Ficha abierta en la tienda. */
  let detailId = $state<string | null>(null);
  let query = $state("");
  let category = $state<(typeof CATEGORIES)[number]>("Todas");
  /** Paquete elegido: se enseña qué trae antes de instalarlo. */
  let choosing = $state(false);

  const devMode = $derived(settings.data?.extensions.dev_mode ?? ext?.devMode ?? false);
  const detail = $derived(STORE.find((e) => e.id === detailId) ?? null);
  const shown = $derived(
    STORE.filter(
      (e) =>
        (category === "Todas" || e.category === category) &&
        `${e.name} ${e.short} ${e.category}`.toLowerCase().includes(query.trim().toLowerCase()),
    ),
  );
  /** La tienda abre con la 1.0: hasta entonces no hay ninguna que se pueda instalar. */
  const storeOpen = $derived((ext?.official.length ?? 0) > 0);

  /** Programas de este PC que se controlan por un puerto conocido: se dice cuál. */
  const KNOWN_PORTS: Record<string, [string, string]> = {
    "localhost:4455": ["Controlar OBS Studio", "grabar, emitir, escenas y fuentes"],
  };

  /** Los permisos en lenguaje normal: [qué puede hacer, matiz]. */
  function describe(p: string): [string, string] {
    const [kind, ...rest] = p.split(":");
    const sub = rest[0] ?? "";
    const target = rest.slice(1).join(":");
    switch (kind) {
      case "net": {
        const where = rest.join(":");
        const known = KNOWN_PORTS[where];
        if (known) return known;
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
          ? ["Abrir apps y sus páginas web", "solo las que Nyx permite"]
          : [`Controlar ${target}`, "su ventana, botones y atajos; nunca en partida"];
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
        return ["Usar el cerebro de Nyx", "con un límite por hora; nunca en partida"];
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

  /** «Cargar una carpeta» (modo desarrollador): se empaqueta y se enseña como un paquete. */
  async function chooseFolder() {
    const path = await open({ multiple: false, directory: true });
    if (typeof path === "string") reload(path);
  }

  function reload(folder: string) {
    choosing = true;
    settings.ext("inspect", undefined, folder);
  }

  function install() {
    const pkg = ext?.inspect;
    if (pkg) settings.ext("install", undefined, pkg.path);
    choosing = false;
  }

  /** Desde la ficha: la oficial que trae Nyx (desde la 1.0). */
  function installFromStore(e: StoreEntry) {
    const offer = ext?.official.find((o) => o.id === e.id);
    if (!offer) return;
    choosing = true;
    settings.ext("inspect", undefined, offer.path);
  }

  function letter(e: { name: string }) {
    return e.name.trim().charAt(0).toUpperCase() || "?";
  }

  function toggle(e: ExtStatus, on: boolean) {
    settings.ext(on ? "enable" : "disable", e.id);
  }

  function installed(id: string): boolean {
    return ext?.items.some((i) => i.id === id) ?? false;
  }

  function manage(id: string) {
    tab = "instaladas";
    openId = id;
  }

  function link(url: string) {
    void invoke("open_link", { url });
  }
</script>

{#if ext}
  <div class="tabs">
    <Segmented
      label="Extensiones"
      options={TABS}
      value={tab}
      onchange={(t) => {
        tab = t;
        detailId = null;
      }}
    />
  </div>

  {#if choosing && ext.inspect}
    {@const pkg = ext.inspect}
    <div class="sheet">
      <div class="head static">
        <span class="icon" aria-hidden="true">{letter(pkg)}</span>
        <span class="grow">
          <span class="name">{pkg.name}</span>
          <span class="hint"
            >{pkg.author} · {pkg.version} · {pkg.signed
              ? "Revisada por Tepnyx"
              : pkg.folder
                ? `Desde ${pkg.folder}`
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
            {@const delicate = pkg.restricted?.includes(p) ?? false}
            <li class:new={delicate && !pkg.signed}>
              {what}{#if why}<span class="why"> · {why}</span>{/if}
              {#if delicate && pkg.why?.[p]}<span class="reason">«{pkg.why[p]}»</span>{/if}
            </li>
          {:else}
            <li>No pide nada: solo contenido, no ejecuta código.</li>
          {/each}
        </ul>
        {#if !pkg.signed && pkg.restricted?.length}
          <p class="problem">
            Pide permisos delicados que Tepnyx aún no ha aprobado: solo funcionan en el modo
            desarrollador. Para publicarla, solicítalos con «nyx_ext.py solicitar».
          </p>
        {/if}
        <div class="line">
          <Button onclick={() => (choosing = false)}>Cancelar</Button>
          <Button primary onclick={install}
            >{pkg.installed_version ? "Actualizar" : "Instalar"}</Button
          >
        </div>
      {:else}
        <p class="problem">
          No la ha revisado Tepnyx. Solo se puede instalar con el modo desarrollador (en
          «Desarrolladores»).
        </p>
        <div class="line">
          <Button onclick={() => (choosing = false)}>Entendido</Button>
        </div>
      {/if}
    </div>
  {/if}
  {#if ext.error}<p class="problem">{ext.error}</p>{/if}

  {#if tab === "tienda"}
    {#if detail}
      {@const e = detail}
      {@const offered = ext.official.some((o) => o.id === e.id)}
      <button class="back" onclick={() => (detailId = null)}>‹ Tienda</button>
      <div class="detail-head">
        <span class="icon big" aria-hidden="true">{letter(e)}</span>
        <span class="grow">
          <span class="title">{e.name}</span>
          <span class="hint"
            >{e.author}{#if e.signed}<span class="tick" title="Revisada por Tepnyx"> ✓</span>{/if} · {e.category}
            · {e.price}</span
          >
        </span>
        {#if installed(e.id)}
          <Button onclick={() => manage(e.id)}>Gestionar</Button>
        {:else if offered}
          <Button primary onclick={() => installFromStore(e)}>Instalar…</Button>
        {:else}
          <span class="badge">Con Nyx {e.since}</span>
        {/if}
      </div>
      {#if !offered && !installed(e.id)}
        <p class="problem">
          Esta extensión se podrá instalar con Nyx {e.since}. En la beta puedes ver lo que hará,
          pero aún no instalarla.
        </p>
      {/if}
      <div class="cols">
        <div class="col">
          <div class="box">
            <span class="box-title">Qué hace</span>
            <p>{e.long}</p>
          </div>
          <div class="box">
            <span class="box-title">Qué puedes decirle</span>
            <div class="says">
              {#each e.says as s (s)}<span>«{s}»</span>{/each}
            </div>
          </div>
          <div class="box">
            <span class="box-title">Lo que necesita</span>
            <ul class="perms">
              {#each e.needs as n (n)}<li>{n}</li>{/each}
            </ul>
          </div>
          <div class="box">
            <span class="box-title">Cómo se prepara</span>
            <ol class="steps">
              {#each e.setup as s (s.text)}
                <li>
                  <span class="name"
                    >{s.text}{#if s.auto}<span class="badge">Lo hace Nyx</span>{/if}</span
                  >
                  <span class="hint">{s.detail}</span>
                </li>
              {/each}
            </ol>
          </div>
        </div>
        <div class="col">
          <div class="box">
            <span class="box-title">Podrá</span>
            <ul class="perms">
              {#each e.permissions as p (p)}
                {@const [what, why] = describe(p)}
                <li>
                  {what}{#if why}<span class="why"> · {why}</span>{/if}
                </li>
              {/each}
            </ul>
            <p class="hint">
              Nunca puede tocar un juego ni saltarse lo que Nyx te pregunta antes de hacer.
            </p>
          </div>
          <div class="box">
            <span class="box-title">Información</span>
            <dl class="facts">
              {#each e.facts as [k, v] (k)}<dt>{k}</dt>
                <dd>{v}</dd>{/each}
            </dl>
          </div>
          {#if e.news.length}
            <div class="box">
              <span class="box-title">Novedades</span>
              {#each e.news as n (n)}<p>{n}</p>{/each}
            </div>
          {/if}
          <div class="box">
            <span class="box-title">Ayuda</span>
            <div class="line start">
              <Button onclick={() => link(STORE_URL)}>Ver en tepnyx.com</Button>
            </div>
          </div>
        </div>
      </div>
    {:else}
      {#if !storeOpen}
        <div class="banner">
          <span class="icon big" aria-hidden="true">✦</span>
          <span class="grow">
            <span class="title">La tienda abre con Nyx 1.0.0</span>
            <span class="hint"
              >Nyx ya está preparada para las extensiones. En la beta puedes ver las primeras y lo
              que harán; se podrán instalar con la 1.0.0. Si haces una, pruébala en
              «Desarrolladores».</span
            >
          </span>
        </div>
      {/if}
      <input
        class="search"
        type="search"
        placeholder="Buscar extensiones"
        aria-label="Buscar extensiones"
        bind:value={query}
      />
      <div class="chips" role="radiogroup" aria-label="Categorías">
        {#each CATEGORIES as c (c)}
          <button
            class="chip"
            class:on={c === category}
            role="radio"
            aria-checked={c === category}
            onclick={() => (category = c)}>{c}</button
          >
        {/each}
      </div>
      {#if !query && category === "Todas"}
        <span class="section">Destacadas</span>
        <div class="featured">
          {#each STORE.filter((s) => s.featured) as e (e.id)}
            <button class="hero" onclick={() => (detailId = e.id)}>
              <span class="hint">{e.category} · {e.price}</span>
              <span class="title">{e.name}</span>
              <span class="hint clamp">{e.short}</span>
              <span class="hero-foot">
                <span class="hint"
                  >{e.author}{#if e.signed}<span class="tick"> ✓</span>{/if}</span
                >
                <span class="badge">{storeOpen ? "Ver" : `Con Nyx ${e.since}`}</span>
              </span>
            </button>
          {/each}
        </div>
      {/if}
      <span class="section">{category}</span>
      {#if shown.length}
        <div class="grid">
          {#each shown as e (e.id)}
            <button class="tile" onclick={() => (detailId = e.id)}>
              <span class="ext">
                <span class="icon" aria-hidden="true">{letter(e)}</span>
                <span class="grow">
                  <span class="name">{e.name}</span>
                  <span class="hint"
                    >{e.author}{#if e.signed}<span class="tick"> ✓</span>{/if}</span
                  >
                </span>
              </span>
              <span class="hint clamp">{e.short}</span>
              <span class="tile-foot">
                <span class="badge">{e.price}</span>
                {#if installed(e.id)}<span class="badge strong">Instalada</span>{/if}
              </span>
            </button>
          {/each}
        </div>
      {:else}
        <p class="empty">
          {query ? `No hay ninguna con «${query}».` : "Aún no hay ninguna en esta categoría."}
        </p>
      {/if}
    {/if}
  {:else if tab === "instaladas"}
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
                {#if e.settings.some((s) => !s.set)}<span class="badge">Falta prepararla</span>{/if}
              </span>
              <span class="hint"
                >{e.author} · {e.version}{e.description ? ` · ${e.description}` : ""}</span
              >
            </span>
          </button>
          <Toggle
            label={`Activar ${e.name}`}
            checked={e.enabled}
            onchange={(on) => toggle(e, on)}
          />
        </div>
        {#if openId === e.id}
          <div class="more">
            {#each e.problems as problem (problem)}<p class="problem">{problem}</p>{/each}
            {#each e.settings as s (s.key)}
              <div class="setting">
                <span class="grow">
                  <span class="label">{s.label}</span>
                  <span class="hint"
                    >{s.hint}{s.secret
                      ? `${s.hint ? " · " : ""}se guarda en el Administrador de credenciales de Windows`
                      : ""}</span
                  >
                </span>
                <span class="field">
                  <TextField
                    label={s.label}
                    secret={s.secret}
                    maxLength={2048}
                    value={s.secret ? "" : (s.value ?? "")}
                    placeholder={s.secret && s.set ? "Guardada" : ""}
                    onchange={(v) => {
                      if (v || !s.secret) settings.extSetting(e.id, s.key, v);
                    }}
                  />
                </span>
                {#if s.secret && s.set}
                  <Button onclick={() => settings.extSetting(e.id, s.key, "")}>Quitar</Button>
                {/if}
              </div>
            {/each}
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
              {#if e.folder}
                <Button onclick={() => reload(e.folder ?? "")}>Recargar</Button>
              {/if}
              <Button
                confirm={`¿Desinstalar ${e.name}? Pulsa otra vez`}
                onclick={() => settings.ext("uninstall", e.id)}>Desinstalar</Button
              >
            </div>
          </div>
        {/if}
      {/each}
      <p class="hint">
        Desinstalar manda la extensión a la papelera y borra sus claves del Administrador de
        credenciales.
      </p>
    </Card>

    <Card title="Añadir">
      <Row label="Desde un archivo" hint="Un .nyxext que te hayas descargado.">
        <Button onclick={() => void choose()}>Elegir archivo…</Button>
      </Row>
    </Card>
  {:else}
    <Card
      title="Para desarrolladores"
      note="Una vez al día Nyx mira si Tepnyx ha retirado alguna extensión (solo si tienes alguna revisada)."
    >
      <Row
        label="Modo desarrollador"
        hint="Instalar extensiones sin revisar para probarlas. Salen como «Sin revisar»."
      >
        <Toggle
          label="Modo desarrollador"
          checked={devMode}
          onchange={(dev_mode) => settings.set({ extensions: { dev_mode } })}
        />
      </Row>
      {#if devMode}
        <Row
          label="Cargar una carpeta"
          hint="La extensión que estás haciendo, sin empaquetarla. Después, «Recargar» la vuelve a leer."
        >
          <Button onclick={() => void chooseFolder()}>Elegir carpeta…</Button>
        </Row>
        <Row label="Desde un archivo" hint="Un .nyxext tuyo, aunque no esté revisado.">
          <Button onclick={() => void choose()}>Elegir archivo…</Button>
        </Row>
      {/if}
      <Row
        label="Guía para hacer extensiones"
        hint="Kit gratuito (MIT): plantillas, pruebas y cómo publicarla en la tienda."
      >
        <Button onclick={() => link(STORE_URL)}>Abrir</Button>
      </Row>
    </Card>

    <Card title="Publicar en la tienda">
      <p class="hint">
        Toda extensión que se publique la revisa Tepnyx: el código, los permisos y que haga lo que
        dice. Al aprobarla, Tepnyx la firma y sale en la tienda. Las que piden permisos delicados
        (escribir archivos, leer el portapapeles, controlar apps, usar el cerebro o mandar mensajes)
        explican para qué en su manifiesto.
      </p>
      <p class="hint">
        Quien publique una extensión aprobada recibe <b>10 € de saldo</b> en su cuenta de Tepnyx.
      </p>
    </Card>
  {/if}
{/if}

<style>
  .tabs {
    display: flex;
    justify-content: flex-start;
  }

  .reason {
    display: block;
    font-size: 12px;
    color: var(--text-secondary);
  }

  .empty {
    margin: 0;
    font-size: 13px;
    color: var(--text-secondary);
  }

  .ext {
    display: flex;
    align-items: center;
    gap: 12px;
    min-width: 0;
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

  .icon.big {
    width: 52px;
    height: 52px;
    border-radius: 16px;
    font-size: 20px;
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

  .title {
    font-weight: 650;
    font-size: 17px;
  }

  .hint {
    margin: 0;
    font-size: 12px;
    color: var(--text-secondary);
  }

  .clamp {
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .tick {
    color: var(--text);
  }

  .badge {
    padding: 2px 8px;
    border-radius: 999px;
    background: var(--control);
    font-size: 11px;
    font-weight: 500;
    color: var(--text-secondary);
    white-space: nowrap;
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

  .setting {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .setting .label {
    font-size: 13px;
    font-weight: 500;
  }

  .setting .field {
    width: 220px;
    flex: none;
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

  .line.start {
    justify-content: flex-start;
  }

  /* --- Tienda (prototipo de 2026-11-15) --- */

  .banner {
    display: flex;
    gap: 14px;
    align-items: center;
    padding: 16px;
    border-radius: 20px;
    background: var(--glass-raised);
  }

  .search {
    width: 100%;
    box-sizing: border-box;
    border: 0;
    border-radius: 999px;
    padding: 10px 16px;
    background: var(--control);
    color: var(--text);
    font: inherit;
    font-size: 13.5px;
    outline: none;
  }

  .chips {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }

  .chip {
    border: 0;
    border-radius: 999px;
    padding: 6px 12px;
    background: var(--control);
    color: var(--text-secondary);
    font: inherit;
    font-size: 12.5px;
    cursor: pointer;
  }

  .chip.on {
    background: var(--control-active);
    color: var(--text-on-active);
  }

  .section {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-secondary);
    margin-top: 4px;
  }

  .featured {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 10px;
  }

  .hero,
  .tile {
    border: 0;
    text-align: left;
    color: inherit;
    font: inherit;
    cursor: pointer;
    display: grid;
    gap: 8px;
    padding: 16px;
    border-radius: 20px;
    background: var(--glass-raised);
    min-width: 0;
  }

  .hero {
    min-height: 140px;
    align-content: space-between;
  }

  .hero-foot,
  .tile-foot {
    display: flex;
    gap: 6px;
    align-items: center;
    justify-content: space-between;
  }

  .tile-foot {
    justify-content: flex-start;
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 10px;
  }

  .back {
    justify-self: start;
    border: 0;
    background: none;
    color: var(--text-secondary);
    font: inherit;
    font-size: 13px;
    padding: 4px 0;
    cursor: pointer;
  }

  .detail-head {
    display: flex;
    gap: 14px;
    align-items: center;
  }

  .cols {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 10px;
  }

  .col {
    display: grid;
    gap: 10px;
    align-content: start;
  }

  .box {
    display: grid;
    gap: 6px;
    padding: 14px;
    border-radius: 18px;
    background: var(--glass-raised);
    font-size: 13px;
  }

  .box p {
    margin: 0;
  }

  .box-title {
    font-weight: 600;
    font-size: 12.5px;
  }

  .says {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .says span {
    padding: 4px 10px;
    border-radius: 999px;
    background: var(--control);
    font-size: 12.5px;
  }

  .steps {
    margin: 0;
    padding-left: 18px;
    display: grid;
    gap: 8px;
  }

  .steps li {
    display: grid;
    gap: 2px;
  }

  .facts {
    margin: 0;
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 4px 12px;
  }

  .facts dt {
    color: var(--text-secondary);
  }

  .facts dd {
    margin: 0;
  }
</style>
