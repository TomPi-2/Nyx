<!--
  Primer arranque, el escaneo del equipo (9.10): programas, juegos y carpetas, y cómo se
  buscan los archivos (con Everything si está; si no, se ofrece instalarlo aquí).
-->
<script lang="ts">
  import type { SetupFlowState } from "$lib/protocol";

  interface Props {
    scan: SetupFlowState["scan"];
    everything: SetupFlowState["everything"];
    installing: boolean;
    oninstall: () => void;
  }
  let { scan, everything, installing, oninstall }: Props = $props();

  const running = $derived(scan === null || scan.running);
  const rows = $derived([
    ["Programas", scan?.apps],
    ["Juegos", scan?.games],
    ["Carpetas", scan?.folders],
  ] as const);
</script>

<div class="rows">
  {#each rows as [name, count] (name)}
    <div class="row">
      <span class="grow">{name}</span>
      <span class="state">{running || count === undefined ? "…" : count}</span>
    </div>
  {/each}
  <div class="row">
    <span class="grow">
      <span class="what">Archivos</span>
      <span class="hint">
        {#if everything.installed}
          Con Everything: todo el disco al instante
        {:else if installing}
          Instalando Everything; Windows te pedirá permiso una vez
        {:else}
          Con el índice de Windows (tus carpetas)
        {/if}
      </span>
    </span>
    {#if !everything.installed && !installing && !running}
      <button class="small" onclick={oninstall}>Instalar Everything</button>
    {:else if everything.installed}
      <span class="state">✓</span>
    {/if}
  </div>
</div>

<style>
  .rows {
    display: grid;
    gap: 6px;
  }

  .row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 14px;
    border-radius: 16px;
    background: var(--glass-raised);
    font-size: 13px;
  }

  .grow {
    flex: 1;
    min-width: 0;
    display: grid;
  }

  .what {
    font-weight: 600;
  }

  .hint {
    font-size: 12px;
    color: var(--text-secondary);
  }

  .state {
    font-size: 12px;
    color: var(--text-secondary);
    font-variant-numeric: tabular-nums;
  }

  .small {
    flex: none;
    padding: 6px 12px;
    border: none;
    border-radius: 999px;
    background: var(--control);
    color: var(--text);
    font: inherit;
    font-size: 12.5px;
    cursor: pointer;
  }
</style>
