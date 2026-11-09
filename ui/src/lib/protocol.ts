// Espejo de core/nyx/bridge/protocol.py: cambia los dos a la vez y sube PROTOCOL_VERSION.

export const PROTOCOL_VERSION = 3;

export type NyxState =
  "idle" | "listening" | "thinking" | "speaking" | "confirm" | "error" | "muted";

export interface Hello {
  type: "hello";
  token: string;
  protocol: number;
}

/** Botón en pastilla de una burbuja (Confirmar, Cancelar, Deshacer). */
export interface ActionButton {
  id: string;
  label: string;
  primary: boolean;
}

/** Interfaz → núcleo (después del hello). */
export type ClientMessage =
  | { type: "text"; text: string }
  | { type: "talk"; pressed: boolean }
  | { type: "action"; id: string };

export type ServerMessage =
  | { type: "welcome"; version: string; protocol: number }
  | { type: "state"; state: NyxState }
  | { type: "level"; rms: number }
  | { type: "bubble"; display: string; secondary: string | null; actions: ActionButton[] }
  | { type: "bubble_hide" };
