// Espejo de core/nyx/bridge/protocol.py: cambia los dos a la vez y sube PROTOCOL_VERSION.

import type { FontId, NyxColorId, PanelTintId } from "$theme/palette";

export const PROTOCOL_VERSION = 18;

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

/** v7: qué panel muestra la burbuja (SPEC sección 11). v17: «long», la respuesta larga. */
export type BubbleKind = "response" | "confirm" | "undo" | "alert" | "long";

/** v17: una parte de una respuesta estructurada («Ingredientes», «Pasos»). */
export interface LongSection {
  title: string;
  items: string[];
  ordered: boolean;
}

/** v8: herramienta para la lista de políticas en partida (Ajustes → Modo partida). */
export interface ToolInfo {
  name: string;
  risk: "green" | "yellow" | "red";
  game_policy: GamePolicy;
}

export type GamePolicy = "allowed" | "deferred" | "blocked";

export type ResponseTone = "cercano" | "neutro" | "divertido";

/**
 * v8: ajustes de settings.json (core/nyx/settings/model.py). Solo se tipan las secciones que
 * cambia la ventana de Ajustes; el resto llega igual pero no se toca.
 */
export interface NyxSettings {
  general: { city: string };
  /** v18: actualizaciones (SPEC §15; tarea 9.05). */
  updates: { mode: "preguntar" | "automatico" | "avisar"; channel: "estable" | "beta" };
  appearance: {
    indicator_size: number;
    glass: GlassInfo;
    /** v10: opciones fijas (theme/palette.ts). */
    font: FontId;
    nyx_color: NyxColorId;
    panel_tint: PanelTintId;
    /** v11: en qué monitor aparece Nyx. */
    monitor: MonitorSettings;
    /** v18: aviso de «Nyx listo» (tarea 9.03). */
    ready_indicator: ReadyIndicator;
  };
  responses: { speak_typed: boolean; tone: ResponseTone };
  wake: {
    enabled: boolean;
    engine: "propio" | "vosk";
    sensitivity: number;
    custom_word: string;
    save_false_clips: boolean;
  };
  listen: { followup_s: number; silence_ms: number };
  tts: { enabled: boolean; voice: string; speed: number };
  /** Nombre del dispositivo; null = el predeterminado de Windows. */
  audio: { input_device: string | null; output_device: string | null };
  /** v12: modelo de Ollama y tiempo máximo de respuesta (Ajustes → Cerebro). */
  llm: { model: string; timeout_s: number };
  onboarding: { done: boolean };
  privacy: { usage_data: boolean };
  /** 6.06: buscar en internet (DuckDuckGo o Wikipedia) y el buscador para el navegador. */
  web: { enabled: boolean; search_url: string };
  game: {
    mode: "off" | "voice" | "normal";
    always: string[];
    never: string[];
    policies: Record<string, GamePolicy>;
    low_priority: boolean;
    unload_llm_after_min: number;
    /** Cerebro en partida: el 7B si cabe junto al juego, o solo reglas (core/nyx/game/brain.py). */
    brain: "auto" | "off";
    /** v11: monitor en partida («solo voz»); null = automático. */
    alt_monitor: string | null;
  };
  [section: string]: unknown;
}

/** v18: cómo avisa Nyx de que está lista (al encender el PC y al instalarse). */
export type ReadyIndicator = "onda" | "nyx" | "nada";

/** v11: en qué monitor aparece Nyx (SPEC sección 11). */
export interface MonitorSettings {
  follow: "cursor" | "fixed";
  /** Dispositivo («\.DISPLAY2»); null = el principal. */
  fixed: string | null;
  /** Animación al cambiar de monitor estando visible. */
  transition: boolean;
}

/** v12: lo que se le puede pedir al asistente (core/nyx/setup/service.py). */
export type SetupAction =
  | "status"
  | "download"
  | "scan"
  | "forget_shortcut"
  | "forget_all_shortcuts" // v16
  | "mic_test_start"
  | "mic_test_stop"
  | "clear_samples"
  | "clear_activations"
  /** v13 */
  | "install_everything"
  | "start_everything";

/** v13: modelo de lenguaje posible (core/nyx/setup/hardware.py). */
export interface LlmChoice {
  id: string;
  label: string;
  size_gb: number;
  min_vram_gb: number;
  note: string;
  tested: boolean;
}

/** v12: estado de modelos, Ollama, whisper, caché, atajos aprendidos y grabaciones. */
export interface SetupStatus {
  models: { key: string; name: string; size_mb: number; license: string; present: boolean }[];
  ollama: { running: boolean; models: string[]; wanted: string; has_wanted: boolean };
  whisper: boolean;
  downloading: boolean;
  index: {
    total: number;
    apps: number;
    games: number;
    folders: number;
    /** Marca de tiempo (segundos) del último escaneo. */
    last_scan: number | null;
    scanning: boolean;
    everything: boolean;
  } | null;
  shortcuts: { phrase: string; tool: string; uses: number }[];
  samples: number;
  activations: number;
  /** v13: tarjeta gráfica, modelos posibles y el recomendado. */
  llm: {
    gpu: { name: string; vram_gb: number } | null;
    choices: LlmChoice[];
    recommended: string;
  };
  /** v13: Everything instalado, abierto y con su línea de órdenes (es.exe). */
  everything: { installed: boolean; running: boolean; cli: boolean };
  installing_everything: boolean;
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
  | { type: "settings_set"; patch: SettingsPatch }
  /** v12 */
  | { type: "setup"; action: SetupAction; arg?: string };

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
      /** v12: si es false, la isla abre el asistente de primer arranque. */
      onboarding_done: boolean;
      /** v18 */
      ready_indicator: ReadyIndicator;
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
      /** v17 (panel largo): el texto entero, las secciones o, con `reading`, nada aún. */
      text?: string;
      sections?: LongSection[];
      reading?: boolean;
    }
  /** v17: panel largo, una frase que empieza a sonar; se escribe en `duration_s` (0: ya). */
  | { type: "reading"; text: string; duration_s: number }
  /** v17: aviso al pie del panel largo; con `undo_action`, botón Deshacer con ese id. */
  | { type: "panel_note"; text: string; undo_action: string | null }
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
  | { type: "open_settings"; section: SettingsSection | null }
  /** v12: asistente y Ajustes → Cerebro, Caché, Ayuda y Privacidad. */
  | { type: "setup_status"; status: SetupStatus }
  | {
      type: "setup_progress";
      key: string;
      label: string;
      done_mb: number;
      total_mb: number;
      finished: boolean;
      error: string | null;
    }
  | { type: "mic_level"; rms: number }
  | { type: "setup_result"; action: string; ok: boolean; message: string | null };

/** Secciones de la ventana de Ajustes (ui/src/settings/Settings.svelte). */
export type SettingsSection =
  | "general"
  | "apariencia"
  | "activacion"
  | "voz"
  | "respuestas"
  | "partida"
  | "cerebro"
  | "cache"
  | "privacidad"
  | "ayuda";
