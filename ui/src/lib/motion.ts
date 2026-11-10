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
  { duration = POP_IN_MS, bounce = true }: { duration?: number; bounce?: boolean } = {},
): { duration: number; easing: (t: number) => number; css: (t: number) => string } {
  return {
    duration,
    // Sin rebote: crece y se para en su tamaño, sin pasarse (contenido grande, como los
    // pasos del asistente, donde el rebote se nota demasiado).
    easing: bounce ? backOut : quartOut,
    css: (t) => `scale: ${t}; opacity: ${Math.min(1, t * 2.5)}`,
  };
}

/**
 * Se cumple cuando `el` termina de encogerse con `pop-out` (app.css), para cerrar la ventana
 * entonces y no a mitad. Un temporizador fijo cortaba el final: la animación empieza uno o
 * dos fotogramas después de pedirla y su último tramo es el más rápido. Hay que llamarlo
 * antes de poner la clase `pop-out`. Si el evento no llega (ventana tapada, «reducir
 * movimiento»), sigue igual tras un margen.
 */
export function popOutDone(el: HTMLElement | undefined): Promise<void> {
  return new Promise((resolve) => {
    let finished = false;
    const finish = () => {
      if (finished) return;
      finished = true;
      el?.removeEventListener("animationend", onEnd);
      clearTimeout(fallback);
      // Un par de fotogramas más para que el último (tamaño 0) llegue a pintarse y al motor
      // de cristal; con la ventana oculta no hay fotogramas, así que también con un tiempo.
      requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
      setTimeout(resolve, 80);
    };
    const onEnd = (e: AnimationEvent) => {
      if (e.target === el && e.animationName === "nyx-pop-out") finish();
    };
    el?.addEventListener("animationend", onEnd);
    const fallback = setTimeout(finish, POP_OUT_MS + 500);
  });
}

function quartOut(t: number): number {
  return 1 - (1 - t) ** 4;
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
