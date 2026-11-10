// Espejo de core/nyx/bridge/protocol.py: cambia los dos a la vez y sube PROTOCOL_VERSION.

import type { FontId, NyxColorId, PanelTintId } from "$theme/palette";

export const PROTOCOL_VERSION = 11;

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

/** v7: ajustes del motor de cristal (Ajustes → Apariencia; SPEC sección 12). */
export interface GlassInfo {
  quality: "auto" | "alto" | "medio" | "bajo";
  motion: "siempre" | "interaccion" | "quieto";
  /** Amplitud del borde: 0–10 → 0–7 px. */
  edge: number;
  /** Los paneles usan el nivel Bajo para salir en capturas y directos. */
  show_in_captures: boolean;
}

/** v7: qué panel muestra la burbuja (SPEC sección 11). */
export type BubbleKind = "response" | "confirm" | "undo" | "alert";

/** v8: herramienta para la lista de políticas en partida (Ajustes → Modo partida). */
export interface ToolInfo {
  name: string;
  risk: "green" | "yellow" | "red";
  game_policy: GamePolicy;
}

export type GamePolicy = "allowed" | "deferred" | "blocked";

/**
 * v8: ajustes de settings.json (core/nyx/settings/model.py). Solo se tipan las secciones que
 * cambia la ventana de Ajustes; el resto llega igual pero no se toca.
 */
export interface NyxSettings {
  appearance: {
    indicator_size: number;
    glass: GlassInfo;
    /** v10: opciones fijas (theme/palette.ts). */
    font: FontId;
    nyx_color: NyxColorId;
    panel_tint: PanelTintId;
    /** v11: en qué monitor aparece Nyx. */
    monitor: MonitorSettings;
  };
  responses: { speak_typed: boolean };
  wake: {
    enabled: boolean;
    engine: "propio" | "vosk";
    sensitivity: number;
    custom_word: string;
  };
  listen: { followup_s: number; silence_ms: number };
  tts: { enabled: boolean; voice: string; speed: number };
  /** Nombre del dispositivo; null = el predeterminado de Windows. */
  audio: { input_device: string | null; output_device: string | null };
  game: {
    mode: "off" | "voice" | "normal";
    always: string[];
    never: string[];
    policies: Record<string, GamePolicy>;
    low_priority: boolean;
    unload_llm_after_min: number;
    /** v11: monitor en partida («solo voz»); null = automático. */
    alt_monitor: string | null;
  };
  [section: string]: unknown;
}

/** v11: en qué monitor aparece Nyx (SPEC sección 11). */
export interface MonitorSettings {
  follow: "cursor" | "fixed";
  /** Dispositivo («\.DISPLAY2»); null = el principal. */
  fixed: string | null;
  /** Animación al cambiar de monitor estando visible. */
  transition: boolean;
}

/** Cambio parcial de ajustes: solo lo que cambia. */
export type SettingsPatch = { [K in keyof NyxSettings]?: Partial<NyxSettings[K]> };

/** Interfaz → núcleo (después del hello). */
export type ClientMessage =
  | { type: "text"; text: string }
  | { type: "talk"; pressed: boolean }
  | { type: "action"; id: string }
  /** v8 */
  | { type: "settings_get" }
  | { type: "settings_set"; patch: SettingsPatch };

export type ServerMessage =
  | {
      type: "welcome";
      version: string;
      protocol: number;
      /** v6: lado de la forma de Nyx en px (Ajustes → Apariencia). */
      indicator_size: number;
      /** v7 */
      glass: GlassInfo;
      /** v10 */
      font: FontId;
      nyx_color: NyxColorId;
      panel_tint: PanelTintId;
    }
  | { type: "state"; state: NyxState }
  | { type: "level"; rms: number }
  | {
      type: "bubble";
      display: string;
      secondary: string | null;
      actions: ActionButton[];
      /** v4: alarmas y avisos; además de la burbuja, notificación de Windows. */
      alert: boolean;
      /** v7 */
      kind: BubbleKind;
      /** v7: cuánto dura (cuenta atrás de confirmar y deshacer), en segundos. */
      expires_s: number | null;
    }
  | { type: "bubble_hide" }
  /** v5: partida en marcha; con «solo voz» o «desactivado» la isla no aparece sobre el juego. */
  | {
      type: "game";
      active: boolean;
      mode: "off" | "voice" | "normal";
      /** v11: monitor del juego («\.DISPLAY1»); "" si no se sabe. */
      monitor: string;
    }
  /** v8: ajustes actuales; llega a todas las ventanas cada vez que cambian. */
  | {
      type: "settings";
      data: NyxSettings;
      /** Lo cambiado que se aplica al reiniciar Nyx. */
      restart: string[];
      /** Cambio rechazado (no se ha aplicado nada). */
      error: string | null;
      tools: ToolInfo[];
      /** v10: micrófonos, altavoces y voces (solo al leerlos). */
      inputs: string[];
      outputs: string[];
      voices: { id: string; label: string }[];
    }
  /** v9: abrir la ventana de Ajustes («abre tus ajustes»), en una sección o en la primera. */
  | { type: "open_settings"; section: SettingsSection | null };

/** Secciones de la ventana de Ajustes (ui/src/settings/Settings.svelte). */
export type SettingsSection = "apariencia" | "activacion" | "voz" | "respuestas" | "partida";
