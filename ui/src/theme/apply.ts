import { dark, light, type NyxPalette } from "./nyx";

const kebab = (s: string) => s.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`);

/** Vuelca la paleta como variables CSS (--glass, --text-secondary…) según el tema de Windows. */
export function applyTheme(): () => void {
  const query = matchMedia("(prefers-color-scheme: dark)");
  const set = () => {
    const palette: NyxPalette = query.matches ? dark : light;
    for (const [key, value] of Object.entries(palette)) {
      document.documentElement.style.setProperty(`--${kebab(key)}`, value);
    }
  };
  set();
  query.addEventListener("change", set);
  return () => query.removeEventListener("change", set);
}
