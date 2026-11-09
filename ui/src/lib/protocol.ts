// Espejo de core/nyx/bridge/protocol.py: cambia los dos a la vez y sube PROTOCOL_VERSION.

export const PROTOCOL_VERSION = 1;

export type NyxState =
  "idle" | "listening" | "thinking" | "speaking" | "confirm" | "error" | "muted";

export interface Hello {
  type: "hello";
  token: string;
  protocol: number;
}

export type ServerMessage =
  | { type: "welcome"; version: string; protocol: number }
  | { type: "state"; state: NyxState }
  | { type: "level"; rms: number }
  | { type: "bubble"; display: string; secondary: string | null }
  | { type: "bubble_hide" };
