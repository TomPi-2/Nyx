/**
 * Ajustes en la ventana de Ajustes (SPEC sección 13): los pide al núcleo y le manda los
 * cambios. Los cambios se ven al momento (se aplican aquí antes de que conteste el núcleo) y
 * el núcleo devuelve los ajustes buenos: si rechaza algo, se vuelve a lo que había.
 */

import { invoke } from "@tauri-apps/api/core";
import { connectCore, type CoreConnection } from "$lib/core";
import type {
  ExtAction,
  ExtInspect,
  ExtStatus,
  NyxSettings,
  NyxState,
  ServerMessage,
  SettingsPatch,
  SetupAction,
  SetupStatus,
  ToolInfo,
} from "$lib/protocol";

/** Una descarga en curso o terminada (asistente y Ajustes → Cerebro). */
export interface Download {
  label: string;
  doneMb: number;
  totalMb: number;
  finished: boolean;
  error: string | null;
}

/** Mientras se arrastra un deslizador no se guarda en cada paso. */
const SAVE_AFTER_MS = 300;
/** Cuánto se ve el aviso de un cambio rechazado («necesita al menos 2 sílabas»…). */
const ERROR_SHOWN_MS = 6000;
/** Tras reiniciar: cada cuánto se pregunta si ya está listo, cuánto se espera como mucho y
    cuánto se ve el aviso de «listo». */
const READY_POLL_MS = 1000;
const READY_TIMEOUT_MS = 90_000;
const READY_SHOWN_MS = 4000;

function merge<T>(base: T, patch: Record<string, unknown>): T {
  const out: Record<string, unknown> = { ...(base as Record<string, unknown>) };
  for (const [key, value] of Object.entries(patch)) {
    const current = out[key];
    const plain = (v: unknown) => typeof v === "object" && v !== null && !Array.isArray(v);
    // Las políticas en partida se sustituyen enteras (igual que en el núcleo).
    out[key] =
      key !== "policies" && plain(value) && plain(current)
        ? merge(current, value as Record<string, unknown>)
        : value;
  }
  return out as T;
}

class SettingsStore {
  data = $state<NyxSettings | null>(null);
  tools = $state<ToolInfo[]>([]);
  /** Micrófonos, altavoces y voces (Ajustes → Voz). */
  inputs = $state<string[]>([]);
  outputs = $state<string[]>([]);
  voices = $state<{ id: string; label: string }[]>([]);
  connected = $state(false);
  /** Asistente y Ajustes → Cerebro, Caché, Ayuda y Privacidad. */
  setupStatus = $state<SetupStatus | null>(null);
  /** Ajustes → Extensiones (7.11): las instaladas, el paquete que se mira y el último fallo. */
  extensions = $state<{
    items: ExtStatus[];
    devMode: boolean;
    inspect: ExtInspect | null;
    error: string | null;
  } | null>(null);
  downloads = $state<Record<string, Download>>({});
  micLevel = $state(0);
  /** Estado de Nyx (el asistente mira si se activa al decir «Nyx»). */
  nyxState = $state<NyxState>("idle");
  lastResult = $state<{ action: string; ok: boolean; message: string | null } | null>(null);
  /** Último cambio rechazado por el núcleo. */
  error = $state<string | null>(null);
  /** Cambios que se aplican al reiniciar Nyx. */
  restart = $state<string[]>([]);
  /** Reiniciando Nyx: hasta que vuelve a estar listo del todo (voz y cerebro cargados). */
  restarting = $state(false);
  /** Aviso breve de que Nyx ya está listo tras reiniciar. */
  readyNotice = $state(false);

  private core: CoreConnection | undefined;
  private pending: SettingsPatch = {};
  private timer: ReturnType<typeof setTimeout> | undefined;
  private errorTimer: ReturnType<typeof setTimeout> | undefined;
  /** Se ha visto caer el núcleo viejo (antes, lo que conteste aún es él). */
  private sawDown = false;
  private readyPoll: ReturnType<typeof setInterval> | undefined;
  private readyTimer: ReturnType<typeof setTimeout> | undefined;

  /** Pide algo al asistente (core/nyx/setup/service.py). */
  setup(action: SetupAction, arg = ""): boolean {
    if (action === "download") this.downloads = {};
    return this.core?.send({ type: "setup", action, arg }) ?? false;
  }

  /** Ajustes → Extensiones (core/nyx/ext/service.py). */
  ext(action: ExtAction, id?: string, path?: string): boolean {
    return this.core?.send({ type: "ext", action, id, path }) ?? false;
  }

  /** v22: guarda un ajuste de una extensión (vacío: lo quita). */
  extSetting(id: string, key: string, value: string): boolean {
    return this.core?.send({ type: "ext", action: "setting", id, key, value }) ?? false;
  }

  /** Primer arranque guiado por Nyx (9.10), otra vez desde Ajustes → Ayuda. */
  startGuidedSetup(): boolean {
    return this.core?.send({ type: "setup_flow", action: "start" }) ?? false;
  }

  /** Reinicia el núcleo para aplicar lo que lo necesita (bandeja → Reiniciar núcleo). */
  async restartCore(): Promise<void> {
    if (this.restarting) return;
    this.restarting = true;
    this.readyNotice = false;
    this.sawDown = false;
    clearTimeout(this.readyTimer);
    await invoke("core_restart");
    this.restart = [];
    // El núcleo nuevo acepta conexiones antes de cargar la voz y el cerebro: está listo
    // cuando el estado trae la caché del sistema, que solo existe con todo en marcha.
    const started = Date.now();
    clearInterval(this.readyPoll);
    this.readyPoll = setInterval(() => {
      if (Date.now() - started > READY_TIMEOUT_MS) {
        this.finishRestart(false);
        return;
      }
      if (this.sawDown && this.connected) this.setup("status");
    }, READY_POLL_MS);
  }

  private finishRestart(ok: boolean): void {
    clearInterval(this.readyPoll);
    this.restarting = false;
    if (!ok) {
      this.error = "Nyx está tardando en volver. Si no aparece, reinícialo desde la bandeja.";
      return;
    }
    this.readyNotice = true;
    clearTimeout(this.readyTimer);
    this.readyTimer = setTimeout(() => (this.readyNotice = false), READY_SHOWN_MS);
  }

  connect(): () => void {
    this.core = connectCore(
      (msg) => this.handle(msg),
      (ok) => {
        this.connected = ok;
        if (!ok) this.sawDown = true;
        if (ok) {
          this.core?.send({ type: "settings_get" });
          this.core?.send({ type: "setup", action: "status" });
          this.core?.send({ type: "ext", action: "list" });
        }
      },
    );
    return () => {
      this.flush();
      this.core?.close();
    };
  }

  /** Cambia y guarda (ya, o tras una pausa si `debounce`). */
  set(patch: SettingsPatch, debounce = false): void {
    if (!this.data) return;
    this.data = merge(this.data, patch as Record<string, unknown>);
    this.pending = merge(this.pending, patch as Record<string, unknown>);
    clearTimeout(this.timer);
    if (debounce) this.timer = setTimeout(() => this.flush(), SAVE_AFTER_MS);
    else this.flush();
  }

  private flush(): void {
    clearTimeout(this.timer);
    if (Object.keys(this.pending).length === 0) return;
    const patch = this.pending;
    this.pending = {};
    if (!this.core?.send({ type: "settings_set", patch })) {
      this.error = "Nyx no está en marcha: el cambio no se ha guardado";
    }
  }

  private handle(msg: ServerMessage): void {
    switch (msg.type) {
      case "setup_status":
        this.setupStatus = msg.status;
        if (this.restarting && this.sawDown && msg.status.index) this.finishRestart(true);
        return;
      case "setup_progress":
        this.downloads = {
          ...this.downloads,
          [msg.key]: {
            label: msg.label,
            doneMb: msg.done_mb,
            totalMb: msg.total_mb,
            finished: msg.finished,
            error: msg.error,
          },
        };
        return;
      case "mic_level":
        this.micLevel = msg.rms;
        return;
      case "state":
        this.nyxState = msg.state;
        return;
      case "extensions":
        this.extensions = {
          items: msg.items,
          devMode: msg.dev_mode,
          inspect: msg.inspect,
          error: msg.error,
        };
        return;
      case "setup_result":
        this.lastResult = { action: msg.action, ok: msg.ok, message: msg.message };
        return;
    }
    if (msg.type !== "settings") return;
    // Si hay cambios esperando a guardarse, no se pisan con lo que llega.
    this.data = Object.keys(this.pending).length
      ? merge(msg.data, this.pending as Record<string, unknown>)
      : msg.data;
    this.tools = msg.tools;
    if (msg.voices.length) this.voices = msg.voices;
    // Los dispositivos solo llegan al leer los ajustes (al abrir Ajustes).
    if (msg.inputs.length || msg.outputs.length) {
      this.inputs = msg.inputs;
      this.outputs = msg.outputs;
    }
    this.error = msg.error;
    // El aviso de un cambio rechazado se va solo (también si llega otro bueno antes).
    clearTimeout(this.errorTimer);
    if (msg.error) this.errorTimer = setTimeout(() => (this.error = null), ERROR_SHOWN_MS);
    // El núcleo dice todo lo pendiente (si se deshace un cambio, deja de estar).
    this.restart = msg.restart;
  }
}

export const settings = new SettingsStore();
