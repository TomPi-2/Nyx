/**
 * Etiqueta propia al pasar el ratón (o al llegar con el teclado), en lugar del `title` nativo
 * de Windows, que no sigue la estética de Nyx (SPEC §12: cristal, redondeada y sin bordes).
 * Hay una sola por ventana; el estilo está en app.css (`.nyx-tooltip`).
 *
 *     <button aria-label="Coral" use:tooltip={"Coral"}>…</button>
 *
 * Solo enseña texto que ya está en `aria-label`: los lectores de pantalla no la necesitan.
 */
import type { Action } from "svelte/action";

/** Lo que tarda en salir al pasar el ratón (con el teclado sale al momento). */
const SHOW_DELAY_MS = 450;
/** Separación con el elemento y margen mínimo con el borde de la ventana. */
const GAP_PX = 8;
const EDGE_PX = 6;

let tip: HTMLDivElement | null = null;
let owner: HTMLElement | null = null;
let timer: ReturnType<typeof setTimeout> | undefined;

function element(): HTMLDivElement {
  if (tip) return tip;
  tip = document.createElement("div");
  tip.className = "nyx-tooltip";
  tip.setAttribute("aria-hidden", "true");
  document.body.appendChild(tip);
  // Si algo se desplaza, la etiqueta ya no está donde debe: se va.
  addEventListener("scroll", () => hide(), true);
  addEventListener("blur", () => hide());
  return tip;
}

/** Encima del elemento (debajo si no cabe), centrada y sin salirse de la ventana. */
function show(target: HTMLElement, text: string): void {
  const el = element();
  owner = target;
  el.textContent = text;
  const r = target.getBoundingClientRect();
  const { offsetWidth: w, offsetHeight: h } = el;
  const center = r.left + r.width / 2;
  let top = r.top - h - GAP_PX;
  const below = top < EDGE_PX;
  if (below) top = r.bottom + GAP_PX;
  const left = Math.min(Math.max(center - w / 2, EDGE_PX), innerWidth - w - EDGE_PX);
  el.style.left = `${left}px`;
  el.style.top = `${top}px`;
  // Crece desde el punto que mira al elemento.
  el.style.transformOrigin = `${center - left}px ${below ? "0" : "100%"}`;
  el.classList.add("on");
}

function hide(target?: HTMLElement): void {
  clearTimeout(timer);
  if (target && owner !== target) return;
  owner = null;
  tip?.classList.remove("on");
}

export const tooltip: Action<HTMLElement, string | undefined> = (node, initial) => {
  let text = initial;
  const enter = () => {
    clearTimeout(timer);
    if (text) timer = setTimeout(() => text && show(node, text), SHOW_DELAY_MS);
  };
  const focus = () => {
    if (text && node.matches(":focus-visible")) show(node, text);
  };
  const leave = () => hide(node);
  const key = (e: KeyboardEvent) => {
    if (e.key === "Escape") hide(node);
  };
  node.addEventListener("pointerenter", enter);
  node.addEventListener("pointerleave", leave);
  node.addEventListener("pointerdown", leave);
  node.addEventListener("focus", focus);
  node.addEventListener("blur", leave);
  node.addEventListener("keydown", key);
  return {
    update(next) {
      text = next;
      if (owner !== node) return;
      if (text) show(node, text);
      else hide(node);
    },
    destroy() {
      node.removeEventListener("pointerenter", enter);
      node.removeEventListener("pointerleave", leave);
      node.removeEventListener("pointerdown", leave);
      node.removeEventListener("focus", focus);
      node.removeEventListener("blur", leave);
      node.removeEventListener("keydown", key);
      hide(node);
    },
  };
};
