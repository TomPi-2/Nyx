import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

const ui = (path: string) => fileURLToPath(new URL(`../ui/src/${path}`, import.meta.url));

// El instalador usa el mismo motor de cristal y la misma forma de Nyx que la app (9.08):
// se importan de ui/src, sin copiarlos.
export default defineConfig({
  plugins: [svelte()],
  clearScreen: false,
  resolve: {
    alias: {
      $lib: ui("lib"),
      $theme: ui("theme"),
      $shape: ui("overlay/shape"),
    },
  },
  // Tauri espera un puerto fijo en desarrollo (tauri.conf.json → devUrl); ui/src está fuera.
  server: { port: 1430, strictPort: true, fs: { allow: [".."] } },
  build: { target: "es2022", outDir: "dist" },
});
