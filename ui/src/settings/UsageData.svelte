<!--
  Qué se enviaría con los datos de uso anónimos y qué nunca (SPEC sección 8). Lo usan Ajustes →
  Privacidad y el último paso del asistente.
-->
<script lang="ts">
  const SENT = [
    "Versión de Nyx y de Windows",
    "Tarjeta gráfica, memoria (por tramos) y modelo de lenguaje",
    "Cuánto tarda Nyx en entender y responder",
    "Qué herramientas se usan (solo el nombre)",
    "Cuántas veces se activa por error",
    "Errores, por tipo",
  ];
  const NEVER = [
    "Audio, transcripciones o frases",
    "Nombres o rutas de archivos y carpetas",
    "Nombres de apps, ventanas o webs",
    "Portapapeles, capturas o grabaciones",
    "Tu ubicación",
    "Identificadores fijos o tu IP",
  ];
</script>

<div class="lists">
  <div>
    <h4>Se enviaría</h4>
    <ul>
      {#each SENT as item (item)}<li>{item}</li>{/each}
    </ul>
  </div>
  <div>
    <h4>Nunca se envía</h4>
    <ul>
      {#each NEVER as item (item)}<li>{item}</li>{/each}
    </ul>
  </div>
</div>

<style>
  .lists {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    padding: 4px 0 12px;
  }

  h4 {
    margin: 0 0 6px;
    font-size: 12px;
    font-weight: 600;
    color: var(--text-secondary);
  }

  ul {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin: 0;
    padding: 0;
    list-style: none;
    font-size: 12px;
    line-height: 1.4;
    color: var(--text-secondary);
  }
</style>
