// Espejo de core/nyx/bridge/protocol.py: cambia los dos a la vez y sube PROTOCOL_VERSION.

export const PROTOCOL_VERSION = 8;

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
  appearance: { indicator_size: number; glass: GlassInfo };
  responses: { speak_typed: boolean };
  game: {
    mode: "off" | "voice" | "normal";
    always: string[];
    never: string[];
    policies: Record<string, GamePolicy>;
    low_priority: boolean;
    unload_llm_after_min: number;
  };
  [section: string]: unknown;
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
  | { type: "game"; active: boolean; mode: "off" | "voice" | "normal" }
  /** v8: ajustes actuales; llega a todas las ventanas cada vez que cambian. */
  | {
      type: "settings";
      data: NyxSettings;
      /** Lo cambiado que se aplica al reiniciar Nyx. */
      restart: string[];
      /** Cambio rechazado (no se ha aplicado nada). */
      error: string | null;
      tools: ToolInfo[];
    };
