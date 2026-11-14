import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// Tauri espera un puerto fijo en desarrollo (tauri.conf.json → devUrl).
export default defineConfig({
  plugins: [svelte()],
  clearScreen: false,
  server: { port: 1430, strictPort: true },
  build: { target: "es2022", outDir: "dist" },
});
