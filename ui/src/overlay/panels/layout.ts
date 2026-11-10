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
