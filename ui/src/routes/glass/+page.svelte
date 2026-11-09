<!--
  Prueba de cristal de la fase 1 (ver src-tauri/src/glass.rs).
  A y B: la ventana tiene Acrylic de Windows; aquí solo se añade el tinte «glass» encima.
  C: ventana transparente; el cristal se imita con tinte y degradado en CSS.
-->
<script lang="ts">
  import { page } from "$app/state";

  const variant = page.url.searchParams.get("v") ?? "a";
  const labels: Record<string, string> = {
    a: "A · Acrylic + esquinas nativas de Windows",
    b: "B · Acrylic + región redondeada (28 px)",
    c: "C · Tinte en CSS, sin desenfoque real",
  };
</script>

{#if variant === "c"}
  <div class="c-stack">
    <div class="c pill"><div class="orb"></div></div>
    <div class="c panel"><span>{labels.c}</span></div>
  </div>
{:else}
  <div class="acrylic" class:pill={variant === "b-pill"}>
    {#if variant === "b-pill"}
      <div class="orb"></div>
    {:else}
      <span>{labels[variant]}</span>
    {/if}
  </div>
{/if}

<style>
  .acrylic {
    width: 100vw;
    height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--glass);
  }

  .c-stack {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 24px;
    padding-top: 8px;
  }

  .c {
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--glass-sheen), var(--glass-fallback);
    box-shadow: var(--shadow);
  }

  .c.pill {
    width: 120px;
    height: 44px;
    border-radius: 22px;
  }

  .c.panel {
    width: 520px;
    height: 120px;
    border-radius: 28px;
  }

  span {
    font-size: 15px;
    font-weight: 600;
    color: var(--text);
  }

  .orb {
    width: 22px;
    height: 22px;
    border-radius: 50%;
    background: radial-gradient(
      circle at 50% 45%,
      var(--glow) 0%,
      rgba(210, 210, 215, 0.85) 38%,
      rgba(150, 150, 158, 0.35) 70%,
      transparent 100%
    );
  }
</style>
