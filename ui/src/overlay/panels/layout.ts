/**
 * Colocación de los paneles respecto a la forma de Nyx (SPEC sección 11, «Nunca se solapan»).
 *
 * La forma se dibuja en un lienzo de `size × SHAPE_PAD` y nunca sale de él (gira, se divide
 * en cuatro, se estira y ondula siempre dentro), así que el borde inferior del lienzo es lo
 * más lejos que puede llegar. Los paneles empiezan 14 px más abajo, más la ondulación de su
 * propio borde: el hueco es fijo y no depende del estado de Nyx (decisión 2026-11-10).
 */

import { SHAPE_PAD } from "../shape/nyxShape";

/** Hueco mínimo entre lo más lejos que llega Nyx y el borde de un panel (px). */
export const PANEL_GAP = 14;
/** Margen superior de la forma en la pantalla (SPEC sección 12). */
export const SHAPE_TOP = 12;
/** Ancho máximo de los paneles de la isla. */
export const PANEL_MAX_WIDTH = 520;
/** Radio de las esquinas de los paneles (SPEC: paneles 24–28 px). */
export const PANEL_RADIUS = 26;

/**
 * Cuando la forma de Nyx se va (por ejemplo, una respuesta escrita sin voz), el panel sube a
 * ocupar su sitio: un panel suelto lejos del borde superior queda mal. Si Nyx vuelve con el
 * panel visible, el panel baja a su hueco y la forma espera PANEL_MOVE_MS para aparecer, así
 * que nunca se tocan.
 *
 * Quién está a la vista lo dice solo la ventana de la forma (Island.svelte) con el evento
 * NYX_EVENT: «gone» cuando la forma ha desaparecido del todo (también tras el «pensando»
 * mínimo y la animación de salida) y «coming» cuando va a aparecer. Deducirlo de los estados
 * del núcleo fallaba: el núcleo pasa a reposo antes de que la forma termine de irse.
 */
export const NYX_EVENT = "island://nyx";
export type NyxPresence = "coming" | "gone";

/** Lo que suele tardar la forma en irse (solo para la vista previa de la galería). */
export const SHAPE_EXIT_MS = 450;
/** Lo que tarda el panel en subir o bajar. */
export const PANEL_MOVE_MS = 280;

/**
 * Sin Nyx, el panel sube hasta donde empieza el cuadrado de Nyx en reposo (no hasta el borde
 * de su lienzo, que deja mucho más aire alrededor): ocupa su sitio sin pegarse al borde.
 */
export function raisedTop(size: number, top = SHAPE_TOP): number {
  return top + (shapeReach(size) - size) / 2;
}

/** Borde inferior de lo que puede ocupar la forma de Nyx, medido desde `top`. */
export function shapeReach(size: number): number {
  return size * SHAPE_PAD;
}

/**
 * Posición vertical del primer panel bajo la forma. `edgePx` es la amplitud del borde líquido
 * de los paneles: la ondulación tampoco puede acercarse más de PANEL_GAP.
 */
export function panelTop(size: number, edgePx: number, top = SHAPE_TOP): number {
  return top + shapeReach(size) + PANEL_GAP + edgePx;
}
