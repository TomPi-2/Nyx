<!--
  Prueba de cristal (ver src-tauri/src/glass.rs): muestra la isla y una burbuja con el
  estilo definitivo de la fase 1 (tinte gris al 84 % + degradado sutil + sombra) para revisar
  la paleta sobre fondos reales.
-->
<div class="stack">
  <div class="glass pill"><div class="orb"></div></div>
  <div class="glass thinking"></div>
  <div class="glass panel">
    <span class="display">Hallo</span>
    <span class="secondary">hola · alemán</span>
  </div>
</div>

<style>
  .stack {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 28px;
    padding: 24px 0 48px;
  }

  .glass {
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--glass-sheen), var(--glass-fallback);
    box-shadow: var(--shadow);
  }

  .pill {
    width: 44px;
    height: 44px;
    border-radius: 22px;
  }

  .thinking {
    width: 120px;
    height: 44px;
    border-radius: 22px;
  }

  .panel {
    flex-direction: column;
    width: 400px;
    height: 96px;
    border-radius: 28px;
  }

  .display {
    font-family: "Segoe UI Variable Display", "Segoe UI", system-ui, sans-serif;
    font-size: 28px;
    font-weight: 600;
    color: var(--text);
  }

  .secondary {
    font-size: 13px;
    color: var(--text-secondary);
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
