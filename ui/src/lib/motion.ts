/**
 * Aparecer y desaparecer como la forma de Nyx (SPEC sección 11): crece desde el centro con
 * un rebote de muelle y, al irse, se encoge hasta desaparecer. Lo usan los paneles, el campo
 * de texto y la ventana de Ajustes con las clases `pop-in` y `pop-out` de app.css; estas
 * duraciones tienen que coincidir con las de allí.
 */

export const POP_IN_MS = 520;
export const POP_OUT_MS = 360;

/**
 * La misma animación como transición de Svelte (`in:pop`, `out:pop`), para lo que aparece y
 * desaparece dentro de una ventana: avisos de Ajustes, desplegables… Al salir se recorre al
 * revés, así que se hincha un poco antes de encogerse.
 */
export function pop(
  _node: Element,
  { duration = POP_IN_MS }: { duration?: number } = {},
): { duration: number; easing: (t: number) => number; css: (t: number) => string } {
  return {
    duration,
    easing: backOut,
    css: (t) => `scale: ${t}; opacity: ${Math.min(1, t * 2.5)}`,
  };
}

/** Pasa un poco de 1 y vuelve (el rebote del muelle). */
function backOut(t: number): number {
  const s = 1.4;
  const u = t - 1;
  return u * u * ((s + 1) * u + s) + 1;
}

/** Cambio de monitor (app.css: `move-out`, `move-in`; island.rs espera MOVE_OUT_MS). */
export const MOVE_OUT_MS = 130;
export const MOVE_IN_MS = 220;
export const MOVE_EVENT = "overlay://move";
export type MovePhase = "out" | "in";
