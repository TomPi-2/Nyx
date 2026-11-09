// Tokens de color de Nyx (SPEC sección 12): solo grises, sin colores de acento.
// Valores iniciales; se afinan en la fase 1 viéndolos sobre fondos reales.

export interface NyxPalette {
  /** Fondo de cristal de paneles y burbujas */
  glass: string;
  /** Tarjetas y grupos dentro de un panel */
  glassRaised: string;
  /** Botones, interruptores apagados, campos */
  control: string;
  /** Interruptor encendido, botón principal */
  controlActive: string;
  /** Texto principal */
  text: string;
  /** Texto secundario */
  textSecondary: string;
  /** Pistas y desactivado */
  textTertiary: string;
  /** Núcleo luminoso del indicador */
  glow: string;
  /** Única forma de separar del fondo */
  shadow: string;
  /** Alternativa sin desenfoque real: tinte gris al 80–85 % (SPEC sección 11) */
  glassFallback: string;
  /** Degradado muy sutil sobre glassFallback para imitar el cristal */
  glassSheen: string;
}

export const dark: NyxPalette = {
  glass: "rgba(28, 28, 30, 0.55)",
  glassRaised: "rgba(58, 58, 60, 0.45)",
  control: "rgba(118, 118, 128, 0.24)",
  controlActive: "rgba(229, 229, 234, 0.90)",
  text: "#F5F5F7",
  textSecondary: "rgba(235, 235, 245, 0.60)",
  textTertiary: "rgba(235, 235, 245, 0.30)",
  glow: "rgba(255, 255, 255, 0.85)",
  shadow: "0 20px 60px rgba(0, 0, 0, 0.35)",
  glassFallback: "rgba(36, 36, 38, 0.84)",
  glassSheen: "linear-gradient(180deg, rgba(255, 255, 255, 0.07), rgba(255, 255, 255, 0) 60%)",
};

export const light: NyxPalette = {
  glass: "rgba(242, 242, 247, 0.60)",
  glassRaised: "rgba(255, 255, 255, 0.55)",
  control: "rgba(118, 118, 128, 0.12)",
  controlActive: "rgba(72, 72, 74, 0.90)",
  text: "#1C1C1E",
  textSecondary: "rgba(60, 60, 67, 0.60)",
  textTertiary: "rgba(60, 60, 67, 0.30)",
  glow: "rgba(255, 255, 255, 0.95)",
  shadow: "0 20px 60px rgba(0, 0, 0, 0.12)",
  glassFallback: "rgba(242, 242, 247, 0.84)",
  glassSheen: "linear-gradient(180deg, rgba(255, 255, 255, 0.45), rgba(255, 255, 255, 0) 60%)",
};

/** Radios en px: paneles 24–28, tarjetas 16–20, controles en pastilla. */
export const radius = {
  panel: 26,
  card: 20,
  pill: 9999,
} as const;

export const font = {
  family: '"Segoe UI Variable", "Segoe UI", system-ui, sans-serif',
  weights: { regular: 400, semibold: 600 },
} as const;
