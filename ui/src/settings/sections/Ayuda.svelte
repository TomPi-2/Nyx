<!-- Ajustes → Ayuda (SPEC sección 13): reiniciar Nyx, repetir el asistente y los registros. -->
<script lang="ts">
  import { invoke } from "@tauri-apps/api/core";
  import Button from "$lib/controls/Button.svelte";
  import Card from "$lib/controls/Card.svelte";
  import Row from "$lib/controls/Row.svelte";
  import { settings } from "../store.svelte";
</script>

<Card title="Si algo va mal">
  <Row
    label="Reiniciar Nyx"
    hint="Vuelve a arrancar la voz y el cerebro de Nyx. También está en el icono de la bandeja."
  >
    <Button onclick={() => void settings.restartCore()}>Reiniciar</Button>
  </Row>
  <Row
    label="Asistente de bienvenida"
    hint="Vuelve a pasar por los pasos del primer arranque: modelos, micrófono, Nyx y tu equipo."
  >
    <Button onclick={() => void invoke("welcome_open")}>Repetir</Button>
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
