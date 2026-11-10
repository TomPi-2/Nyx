/**
 * Monitores conectados, para Ajustes → Apariencia («Monitor») y Modo partida («Monitor en
 * partida»). Se vuelve a mirar cada pocos segundos mientras la sección está abierta: si se
 * conecta o desconecta un monitor, las opciones se desbloquean o bloquean solas.
 */

import { invoke } from "@tauri-apps/api/core";

export interface MonitorInfo {
  device: string;
  label: string;
  primary: boolean;
}

const REFRESH_MS = 2000;

class Monitors {
  list = $state<MonitorInfo[]>([]);

  /** Con uno solo no hay nada que elegir: las opciones se ven bloqueadas. */
  get single(): boolean {
    return this.list.length < 2;
  }

  get primary(): MonitorInfo | undefined {
    return this.list.find((m) => m.primary) ?? this.list[0];
  }

  /** Empieza a mirar; devuelve la función para parar (para onMount). */
  watch(): () => void {
    const refresh = async () => {
      try {
        this.list = await invoke<MonitorInfo[]>("monitors_list");
      } catch {
        this.list = [];
      }
    };
    void refresh();
    const timer = setInterval(() => void refresh(), REFRESH_MS);
    return () => clearInterval(timer);
  }
}

export const monitors = new Monitors();
