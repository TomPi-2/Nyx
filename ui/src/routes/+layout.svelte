<script lang="ts">
  import { onMount, type Snippet } from "svelte";
  import { applyTheme } from "$theme/apply";
  import "../app.css";

  let { children }: { children: Snippet } = $props();

  onMount(() => applyTheme());
</script>

{@render children()}
