/**
 * Apariencia personalizable (SPEC sección 12): opciones fijas, nunca una paleta libre.
 * Los valores son los que se aprobaron en docs/prototipos/apariencia.html. Los nombres
 * (claves) son los de core/nyx/settings/model.py (Font, NyxColor, PanelTint).
 */

import manropeLatinExt from "@fontsource-variable/manrope/files/manrope-latin-ext-wght-normal.woff2?url";
import manropeLatin from "@fontsource-variable/manrope/files/manrope-latin-wght-normal.woff2?url";
import nunitoLatinExt from "@fontsource-variable/nunito/files/nunito-latin-ext-wght-normal.woff2?url";
import nunitoLatin from "@fontsource-variable/nunito/files/nunito-latin-wght-normal.woff2?url";

export type FontId = "segoe" | "manrope" | "nunito";
export type NyxColorId =
  | "blanco"
  | "perla"
  | "arena"
  | "melocoton"
  | "coral"
  | "rojo"
  | "rosa"
  | "fucsia"
  | "lavanda"
  | "violeta"
  | "azul_cielo"
  | "azul"
  | "turquesa"
  | "menta"
  | "verde"
  | "lima"
  | "amarillo"
  | "ambar"
  | "grafito";
export type PanelTintId =
  | "gris"
  | "grafito"
  | "azul_noche"
  | "oceano"
  | "bosque"
  | "salvia"
  | "ciruela"
  | "vino"
  | "rosa"
  | "arena"
  | "cobre"
  | "lavanda";

type Rgb = [number, number, number];

// --- Fuentes -------------------------------------------------------------------------------

/** Solo los caracteres latinos (español y lenguas de Europa occidental): lo demás no se usa. */
const LATIN =
  "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD";
const LATIN_EXT =
  "U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+0304,U+0308,U+0329,U+1D00-1DBF,U+1E00-1E9F,U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C0,U+2113,U+2C60-2C7F,U+A720-A7FF";

interface FontOption {
  label: string;
  /** Texto normal y títulos (Segoe tiene una versión «Display» para tamaños grandes). */
  text: string;
  display: string;
  /** Archivos de la fuente incluidos en Nyx (licencia SIL OFL); Segoe viene con Windows. */
  files?: { family: string; latin: string; latinExt: string };
}

export const FONTS: Record<FontId, FontOption> = {
  segoe: {
    label: "Segoe UI",
    text: '"Segoe UI Variable Text", "Segoe UI Variable", "Segoe UI", system-ui, sans-serif',
    display: '"Segoe UI Variable Display", "Segoe UI Variable", "Segoe UI", system-ui, sans-serif',
  },
  manrope: {
    label: "Manrope",
    text: '"Manrope Variable", "Segoe UI", system-ui, sans-serif',
    display: '"Manrope Variable", "Segoe UI", system-ui, sans-serif',
    files: { family: "Manrope Variable", latin: manropeLatin, latinExt: manropeLatinExt },
  },
  nunito: {
    label: "Nunito",
    text: '"Nunito Variable", "Segoe UI", system-ui, sans-serif',
    display: '"Nunito Variable", "Segoe UI", system-ui, sans-serif',
    files: { family: "Nunito Variable", latin: nunitoLatin, latinExt: nunitoLatinExt },
  },
};

const loaded = new Set<FontId>();

/** Carga los archivos de una fuente incluida (solo la primera vez que se elige). */
export async function loadFont(id: FontId): Promise<void> {
  const files = FONTS[id].files;
  if (!files || loaded.has(id)) return;
  loaded.add(id);
  const faces = [
    new FontFace(files.family, `url(${files.latin})`, {
      weight: "200 1000",
      unicodeRange: LATIN,
      display: "swap",
    }),
    new FontFace(files.family, `url(${files.latinExt})`, {
      weight: "200 1000",
      unicodeRange: LATIN_EXT,
      display: "swap",
    }),
  ];
  for (const face of faces) document.fonts.add(face);
  await Promise.allSettled(faces.map((f) => f.load()));
}

// --- Color de Nyx --------------------------------------------------------------------------

/** Opacos y suaves: la forma se sigue leyendo como un sólido sobre cualquier fondo. */
export const NYX_COLORS: Record<NyxColorId, { label: string; hex: string }> = {
  blanco: { label: "Blanco", hex: "#ffffff" },
  perla: { label: "Perla", hex: "#ebe8e2" },
  arena: { label: "Arena", hex: "#ead7b7" },
  melocoton: { label: "Melocotón", hex: "#ffcaa9" },
  coral: { label: "Coral", hex: "#ff8f80" },
  rojo: { label: "Rojo", hex: "#e5484d" },
  rosa: { label: "Rosa", hex: "#ffb6c9" },
  fucsia: { label: "Fucsia", hex: "#f277b6" },
  lavanda: { label: "Lavanda", hex: "#cbbcff" },
  violeta: { label: "Violeta", hex: "#a184ff" },
  azul_cielo: { label: "Azul cielo", hex: "#a3d5ff" },
  azul: { label: "Azul", hex: "#5a93ff" },
  turquesa: { label: "Turquesa", hex: "#62d8d1" },
  menta: { label: "Menta", hex: "#a5e9c6" },
  verde: { label: "Verde", hex: "#62c78f" },
  lima: { label: "Lima", hex: "#d8f17f" },
  amarillo: { label: "Amarillo", hex: "#ffe383" },
  ambar: { label: "Ámbar", hex: "#ffb84d" },
  grafito: { label: "Grafito", hex: "#4a4a4f" },
};

/** Color de Nyx en 0–1 para el shader. */
export function nyxRgb(id: string): Rgb {
  const hex = (NYX_COLORS[id as NyxColorId] ?? NYX_COLORS.blanco).hex;
  const n = parseInt(hex.slice(1), 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}

// --- Tinte de los paneles ------------------------------------------------------------------

/** Cada tinte tiene versión para el tema oscuro y para el claro (texto siempre legible). */
export const PANEL_TINTS: Record<PanelTintId, { label: string; dark: Rgb; light: Rgb }> = {
  gris: { label: "Gris", dark: [28, 28, 30], light: [242, 242, 247] },
  grafito: { label: "Grafito", dark: [18, 18, 22], light: [225, 225, 230] },
  azul_noche: { label: "Azul noche", dark: [20, 28, 52], light: [226, 234, 250] },
  oceano: { label: "Océano", dark: [14, 44, 58], light: [222, 240, 246] },
  bosque: { label: "Bosque", dark: [18, 42, 30], light: [224, 242, 230] },
  salvia: { label: "Salvia", dark: [40, 48, 38], light: [234, 240, 228] },
  ciruela: { label: "Ciruela", dark: [44, 24, 52], light: [240, 228, 246] },
  vino: { label: "Vino", dark: [54, 20, 30], light: [248, 228, 232] },
  rosa: { label: "Rosa", dark: [60, 30, 44], light: [252, 232, 240] },
  arena: { label: "Arena", dark: [52, 44, 30], light: [246, 238, 224] },
  cobre: { label: "Cobre", dark: [58, 34, 22], light: [250, 234, 222] },
  lavanda: { label: "Lavanda", dark: [38, 34, 64], light: [236, 232, 252] },
};

export function panelTint(id: string): { dark: Rgb; light: Rgb } {
  return PANEL_TINTS[id as PanelTintId] ?? PANEL_TINTS.gris;
}
