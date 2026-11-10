import { dark, light, type NyxPalette } from "./nyx";
import { FONTS, loadFont, panelTint, type FontId } from "./palette";

const kebab = (s: string) => s.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`);
const query = matchMedia("(prefers-color-scheme: dark)");

/** Tinte de los paneles elegido en Apariencia (null = el gris de la paleta). */
let tint: { dark: [number, number, number]; light: [number, number, number] } | null = null;

function set(): void {
  const palette: NyxPalette = query.matches ? dark : light;
  const root = document.documentElement.style;
  for (const [key, value] of Object.entries(palette)) {
    root.setProperty(`--${kebab(key)}`, value);
  }
  // El tinte de respaldo (si el motor de cristal no puede dibujar) sigue al elegido.
  if (tint) {
    const [r, g, b] = query.matches ? tint.dark : tint.light;
    root.setProperty("--glass-fallback", `rgba(${r}, ${g}, ${b}, 0.84)`);
  }
}

/** Vuelca la paleta como variables CSS (--glass, --text-secondary…) según el tema de Windows. */
export function applyTheme(): () => void {
  set();
  query.addEventListener("change", set);
  return () => query.removeEventListener("change", set);
}

/**
 * Fuente elegida en Apariencia: la carga (Manrope y Nunito van dentro de Nyx) y la pone en
 * las variables --font-text y --font-display que usa toda la interfaz.
 */
export function applyFont(id: string): void {
  const font = FONTS[id as FontId] ?? FONTS.segoe;
  void loadFont(id as FontId);
  const root = document.documentElement.style;
  root.setProperty("--font-text", font.text);
  root.setProperty("--font-display", font.display);
}

/** Tinte de los paneles elegido en Apariencia, para el tinte de respaldo en CSS. */
export function applyPanelTint(id: string): void {
  tint = id === "gris" ? null : panelTint(id);
  set();
}

/** Todo lo que llega del núcleo en «welcome» o en «settings». */
export function applyAppearance(a: { font?: string; panel_tint?: string }): void {
  if (a.font) applyFont(a.font);
  if (a.panel_tint) applyPanelTint(a.panel_tint);
}
