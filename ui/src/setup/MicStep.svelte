<!--
  Primer arranque, el micrófono (9.10): elegirlo, ver la barra con tu voz en directo y la
  prueba de decir «Nyx». Va primero para que todo lo demás se pueda contestar hablando. También
  por dónde suena Nyx: si la salida de Windows no es la buena, no se la oye (ERRORES.md,
  2026-11-14); al elegir otra, pregunta «¿Me oyes bien por aquí?».
-->
<script lang="ts">
  interface Props {
    mics: string[];
    mic: string | null;
    speakers: string[];
    speaker: string | null;
    level: number;
    heard: boolean;
    woke: boolean;
    onpick: (index: number) => void;
    onspeaker: (index: number) => void;
  }
  let { mics, mic, speakers, speaker, level, heard, woke, onpick, onspeaker }: Props = $props();

  // Sin elegir, el predeterminado de Windows (el primero de la lista).
  const selected = $derived(Math.max(0, mic === null ? 0 : mics.indexOf(mic)));
  const selectedOut = $derived(Math.max(0, speaker === null ? 0 : speakers.indexOf(speaker)));
</script>

{#if mics.length > 1}
  <div class="group">
    <span class="label">Micrófono</span>
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
  </div>
{/if}
{#if speakers.length > 1}
  <div class="group">
    <span class="label">Por dónde suena Nyx</span>
    <div class="pills" role="radiogroup" aria-label="Por dónde suena Nyx">
      {#each speakers as name, i (name)}
        <button
          role="radio"
          aria-checked={i === selectedOut}
          class:on={i === selectedOut}
          onclick={() => i !== selectedOut && onspeaker(i)}>{name}</button
        >
      {/each}
    </div>
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
  .group {
    display: grid;
    gap: 6px;
  }

  .label {
    font-size: 12px;
    color: var(--text-secondary);
  }

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
