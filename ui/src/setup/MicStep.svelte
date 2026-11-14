<!--
  Primer arranque, el micrófono (9.10): elegirlo, ver la barra con tu voz en directo y la
  prueba de decir «Nyx». Va primero para que todo lo demás se pueda contestar hablando.
-->
<script lang="ts">
  interface Props {
    mics: string[];
    mic: string | null;
    level: number;
    heard: boolean;
    woke: boolean;
    onpick: (index: number) => void;
  }
  let { mics, mic, level, heard, woke, onpick }: Props = $props();

  // Sin elegir, el predeterminado de Windows (el primero de la lista).
  const selected = $derived(Math.max(0, mic === null ? 0 : mics.indexOf(mic)));
</script>

{#if mics.length > 1}
  <div class="pills" role="radiogroup" aria-label="Micrófono">
    {#each mics as name, i (name)}
      <button
        role="radio"
        aria-checked={i === selected}
        class:on={i === selected}
        onclick={() => i !== selected && onpick(i)}>{name}</button
      >
    {/each}
  </div>
{/if}
<div class="meter" aria-hidden="true"><i style:width="{Math.round(level * 100)}%"></i></div>
<p class="hint" class:done={woke}>
  {#if woke}
    ✓ Me activo con tu voz. Ya puedes contestarme hablando.
  {:else if heard}
    Ahora di «Nyx».
  {:else}
    Habla un poco, lo que quieras.
  {/if}
</p>

<style>
  .pills {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .pills button {
    padding: 7px 13px;
    border: none;
    border-radius: 999px;
    background: var(--control);
    color: var(--text);
    font: inherit;
    font-size: 12.5px;
    cursor: pointer;
  }

  .pills button.on {
    background: var(--control-active);
    color: var(--text-on-active);
  }

  .meter {
    height: 8px;
    border-radius: 999px;
    background: var(--control);
    overflow: hidden;
  }

  .meter i {
    display: block;
    height: 100%;
    border-radius: 999px;
    background: var(--control-active);
    transition: width 80ms linear;
  }

  .hint {
    margin: 0;
    font-size: 12.5px;
    color: var(--text-secondary);
  }

  .hint.done {
    color: var(--text);
  }
</style>
