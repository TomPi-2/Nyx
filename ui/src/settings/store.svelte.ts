/**
 * Ajustes en la ventana de Ajustes (SPEC sección 13): los pide al núcleo y le manda los
 * cambios. Los cambios se ven al momento (se aplican aquí antes de que conteste el núcleo) y
 * el núcleo devuelve los ajustes buenos: si rechaza algo, se vuelve a lo que había.
 */

import { connectCore, type CoreConnection } from "$lib/core";
import type { NyxSettings, ServerMessage, SettingsPatch, ToolInfo } from "$lib/protocol";

/** Mientras se arrastra un deslizador no se guarda en cada paso. */
const SAVE_AFTER_MS = 300;

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
  connected = $state(false);
  /** Último cambio rechazado por el núcleo. */
  error = $state<string | null>(null);
  /** Cambios que se aplican al reiniciar Nyx. */
  restart = $state<string[]>([]);

  private core: CoreConnection | undefined;
  private pending: SettingsPatch = {};
  private timer: ReturnType<typeof setTimeout> | undefined;

  connect(): () => void {
    this.core = connectCore(
      (msg) => this.handle(msg),
      (ok) => {
        this.connected = ok;
        if (ok) this.core?.send({ type: "settings_get" });
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
    if (msg.type !== "settings") return;
    // Si hay cambios esperando a guardarse, no se pisan con lo que llega.
    this.data = Object.keys(this.pending).length
      ? merge(msg.data, this.pending as Record<string, unknown>)
      : msg.data;
    this.tools = msg.tools;
    this.error = msg.error;
    if (msg.restart.length) this.restart = [...new Set([...this.restart, ...msg.restart])];
  }
}

export const settings = new SettingsStore();
