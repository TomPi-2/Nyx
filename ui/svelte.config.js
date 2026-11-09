// Tauri no tiene servidor Node para SSR: adapter-static en modo SPA (fallback a index.html).
// https://v2.tauri.app/start/frontend/sveltekit/
import adapter from "@sveltejs/adapter-static";
import { vitePreprocess } from "@sveltejs/vite-plugin-svelte";

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter({ fallback: "index.html" }),
    alias: {
      $theme: "src/theme",
      $overlay: "src/overlay",
    },
  },
};

export default config;
