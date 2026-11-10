/**
 * Motor de cristal desde la interfaz (src-tauri/src/glass).
 *
 * Cada ventana tiene una lámina: los paneles se registran con la acción `glassShape` y el
 * motor dibuja detrás de la WebView el cristal con su silueta líquida. Si el motor no
 * puede dibujar (sin GPU, error), `<html data-glass="css">` activa el tinte de CSS de
 * siempre (app.css), así que la interfaz nunca se queda sin fondo.
 */

import { invoke } from "@tauri-apps/api/core";
import type { UnlistenFn } from "@tauri-apps/api/event";
import { getCurrentWebviewWindow } from "@tauri-apps/api/webviewWindow";
import type { GlassInfo } from "./protocol";

/**
 * Lo que elige el usuario (decisión del 2026-11-10). En Auto el motor baja solo (batería,
 * ahorro de energía, transparencias de Windows, GPU que no llega). Con un nivel concreto se
 * respeta, salvo en partida: ahí se pasa a Bajo sin excepción.
 */
export type GlassPreference = "auto" | "alto" | "medio" | "bajo";
/** Lo que dibuja el motor, de menos a más coste. */
export type GlassLevel = "bajo" | "medio" | "alto";
export type GlassMotion = "siempre" | "interaccion" | "quieto";

/**
 * Amplitud del borde en Ajustes: una barra de 0 a 10, de 1 en 1, que va de 0 a 7 px; el 5 (3,5 px) es
 * el valor predeterminado.
 */
export const EDGE_LEVEL_DEFAULT = 5;
export const EDGE_PX_PER_LEVEL = 0.7;
export const edgeLevelToPx = (level: number) => Math.round(level * EDGE_PX_PER_LEVEL * 100) / 100;
/** Nivel entero de 0 a 10 (la barra va de 1 en 1). */
export const edgePxToLevel = (px: number) =>
  Math.min(10, Math.max(0, Math.round(px / EDGE_PX_PER_LEVEL)));

export interface GlassOptions {
  quality: GlassPreference;
  motion: GlassMotion;
  /** Amplitud del borde líquido (px, 0–7). */
  amplitude: number;
  /** Velocidad de la ondulación (1 = normal). */
  speed: number;
  /** Cantidad de desenfoque (0–1). */
  blur: number;
  /** Opacidad del tinte gris sobre el cristal (0–1). */
  tint: number;
  /** Desplazamiento máximo de la refracción junto al borde (px). */
  refraction: number;
  saturation: number;
  specular: number;
  shadow: number;
  /** Tema oscuro de Windows. */
  dark: boolean;
}

/** Valores elegidos por el usuario en la galería (2026-11-10). */
export const DEFAULT_GLASS: GlassOptions = {
  quality: "auto",
  motion: "siempre",
  amplitude: edgeLevelToPx(EDGE_LEVEL_DEFAULT),
  speed: 1,
  blur: 0.6,
  tint: 0.45,
  refraction: 10,
  saturation: 1.15,
  specular: 0.35,
  shadow: 0.4,
  dark: true,
};

export interface GlassStats {
  requested: GlassPreference;
  effective: GlassLevel;
  reason: string | null;
  fps: number;
  gpuMs: number | null;
  gpuLoad: number | null;
  captureFps: number | null;
  adapter: string;
  animating: boolean;
  failed: string | null;
}

export interface ShapeOptions {
  /** Radio de las esquinas (px). */
  radius: number;
  /** Amplitud del borde de este panel respecto a la general (1 = igual, 0 = sin onda). */
  wobble?: number;
}

const MAX_SHAPES = 8;
/** Por debajo de este tamaño (px), el borde ondula menos cuanto más pequeño. */
const SMALL_PX = 48;

function prefersDark(): boolean {
  return matchMedia("(prefers-color-scheme: dark)").matches;
}

class GlassSurface {
  private shapes = new Map<HTMLElement, ShapeOptions>();
  private resize = new ResizeObserver(() => this.refresh());
  private frame = 0;
  private attached = false;
  private options: GlassOptions = { ...DEFAULT_GLASS, dark: prefersDark() };

  /** Empieza a usar el motor en esta ventana. */
  async attach(options: Partial<GlassOptions> = {}): Promise<void> {
    this.options = { ...this.options, ...options };
    try {
      await invoke("glass_attach", { options: this.options });
      this.attached = true;
      this.setFallback(false);
      this.refresh();
    } catch (err) {
      console.warn("Motor de cristal no disponible:", err);
      this.setFallback(true);
    }
    // El tema de Windows cambia el tinte.
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", (e) =>
      this.set({ dark: e.matches }),
    );
  }

  detach(): void {
    if (this.attached) void invoke("glass_detach");
    this.attached = false;
  }

  get current(): GlassOptions {
    return this.options;
  }

  set(options: Partial<GlassOptions>): void {
    this.options = { ...this.options, ...options };
    if (this.attached) void invoke("glass_set_options", { options: this.options });
  }

  /** Aparecer, pasar el ratón, pulsar: en el modo «al interactuar» el borde ondula un rato. */
  poke(): void {
    if (this.attached) void invoke("glass_poke");
  }

  /** Partida en curso: el motor deja de capturar la pantalla. */
  setGame(active: boolean): void {
    void invoke("glass_set_game", { active });
  }

  onStats(callback: (stats: GlassStats) => void): Promise<UnlistenFn> {
    return getCurrentWebviewWindow().listen<GlassStats>("glass-stats", (e) => {
      if (e.payload.failed) this.setFallback(true);
      callback(e.payload);
    });
  }

  add(el: HTMLElement, options: ShapeOptions): void {
    if (this.shapes.size >= MAX_SHAPES) {
      console.warn(`El motor de cristal admite ${MAX_SHAPES} paneles por ventana`);
      return;
    }
    this.shapes.set(el, options);
    el.classList.add("glass-shape");
    this.resize.observe(el);
    this.refresh();
  }

  update(el: HTMLElement, options: ShapeOptions): void {
    if (!this.shapes.has(el)) return;
    this.shapes.set(el, options);
    this.refresh();
  }

  remove(el: HTMLElement): void {
    this.shapes.delete(el);
    this.resize.unobserve(el);
    el.classList.remove("glass-shape");
    this.refresh();
  }

  /**
   * Sigue a los paneles durante una animación (aparecer, desaparecer, crecer): manda las
   * formas en cada fotograma durante `ms`.
   */
  follow(ms: number): void {
    const end = performance.now() + ms;
    const step = () => {
      this.flush();
      if (performance.now() < end) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  /**
   * Vuelve a mandar las formas en el siguiente fotograma. Los cambios de tamaño se ven
   * solos; si un panel se mueve (animación, cambio de diseño), hay que llamarlo.
   */
  refresh(): void {
    if (this.frame) return;
    this.frame = requestAnimationFrame(() => {
      this.frame = 0;
      this.flush();
    });
  }

  private flush(): void {
    if (!this.attached) return;
    const shapes = [...this.shapes].map(([el, o]) => {
      const r = el.getBoundingClientRect();
      // Al encogerse (aparecer y desaparecer), un panel diminuto deja de ondular: si no,
      // quedaría una gotita temblando al final.
      const small = Math.min(1, Math.min(r.width, r.height) / SMALL_PX);
      return {
        x: r.x,
        y: r.y,
        w: r.width,
        h: r.height,
        radius: o.radius,
        wobble: (o.wobble ?? 1) * small,
      };
    });
    void invoke("glass_set_shapes", { shapes });
  }

  private setFallback(on: boolean): void {
    document.documentElement.dataset.glass = on ? "css" : "engine";
  }
}

/**
 * Opciones del motor a partir de los ajustes que manda el núcleo (Ajustes → Apariencia).
 * «Mostrar Nyx en capturas y directos» pasa los paneles a Bajo: así no capturan la pantalla
 * y no hace falta excluirlos de las capturas.
 */
export function glassFromSettings(info: GlassInfo): Partial<GlassOptions> {
  return {
    quality: info.show_in_captures ? "bajo" : info.quality,
    motion: info.motion,
    amplitude: edgeLevelToPx(info.edge),
  };
}

/** La lámina de esta ventana (una por ventana). */
export const glass = new GlassSurface();

/** Acción de Svelte: al pasar el ratón o pulsar, el borde ondula (modo «al interactuar»). */
export function glassPoke(node: HTMLElement) {
  const poke = () => glass.poke();
  node.addEventListener("pointerenter", poke);
  node.addEventListener("pointerdown", poke);
  return {
    destroy() {
      node.removeEventListener("pointerenter", poke);
      node.removeEventListener("pointerdown", poke);
    },
  };
}

/** Acción de Svelte: `<div use:glassShape={{ radius: 26 }}>` pone ese panel sobre cristal. */
export function glassShape(node: HTMLElement, options: ShapeOptions) {
  glass.add(node, options);
  return {
    update(next: ShapeOptions) {
      glass.update(node, next);
    },
    destroy() {
      glass.remove(node);
    },
  };
}
