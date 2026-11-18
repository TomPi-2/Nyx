/**
 * La tienda de extensiones de Ajustes (prototipo aprobado el 2026-11-15,
 * docs/prototipos/tienda-extensiones.html). La beta enseña la tienda, pero las extensiones
 * llegan con Nyx 1.0.0 (decisión 2026-11-15): aquí, las fichas de las primeras, con los datos de
 * sus manifiestos (extensions/tepnyx.*). Cuando abra la tienda, el catálogo vendrá de Tepnyx
 * (como en la web, tepnyx.com/nyx/extensiones) y estas fichas se quitan.
 */

export type StoreCategory =
  "Streaming" | "Música" | "Productividad" | "Hogar" | "Formas" | "Juegos";

export const CATEGORIES: ("Todas" | StoreCategory)[] = [
  "Todas",
  "Streaming",
  "Música",
  "Productividad",
  "Hogar",
  "Formas",
  "Juegos",
];

export interface SetupStep {
  /** Lo hace Nyx sola (se marca en la ficha). */
  auto: boolean;
  text: string;
  detail: string;
}

export interface StoreEntry {
  id: string;
  name: string;
  author: string;
  /** Revisada y firmada por Tepnyx (toda extensión publicada lo está). */
  signed: boolean;
  category: StoreCategory;
  price: string;
  short: string;
  long: string;
  says: string[];
  needs: string[];
  setup: SetupStep[];
  /** Permisos con su forma exacta (se describen como en «Instaladas»). */
  permissions: string[];
  facts: [string, string][];
  news: string[];
  featured: boolean;
  /** Desde qué versión de Nyx se puede instalar. */
  since: string;
}

export const STORE: StoreEntry[] = [
  {
    id: "tepnyx.obs",
    name: "OBS Studio",
    author: "Tepnyx",
    signed: true,
    category: "Streaming",
    price: "Gratis",
    short:
      "Graba, emite, cambia de escena, silencia fuentes y guarda repeticiones en OBS con la voz.",
    long: "Controla OBS por su servidor WebSocket, sin teclas ni atajos: empezar, parar, pausar y reanudar la grabación; empezar y terminar el directo (te pregunta antes); guardar la repetición; la cámara virtual; cambiar de escena por su nombre; silenciar o cambiar el volumen del micro, del PC o de una fuente; mostrar u ocultar fuentes; hacer una captura; y decirte si está grabando o emitiendo.",
    says: [
      "Nyx, empieza a grabar",
      "Pon la escena de charla",
      "Silencia el micro en OBS",
      "Guarda la repetición",
      "¿Estoy en directo?",
    ],
    needs: ["OBS Studio 28 o posterior, abierto", "Su servidor WebSocket activado"],
    setup: [
      {
        auto: false,
        text: "Activa el servidor WebSocket en OBS",
        detail:
          "Herramientas → Configuración del servidor WebSocket → «Habilitar servidor WebSocket» (puerto 4455).",
      },
      {
        auto: false,
        text: "Pega su contraseña en Nyx",
        detail:
          "«Mostrar información de conexión» en OBS, y aquí en Instaladas → OBS Studio. Si no tiene, nada.",
      },
      {
        auto: true,
        text: "Conectarse a OBS",
        detail: "Nyx se conecta sola cada vez que se lo pidas, con OBS abierto.",
      },
    ],
    permissions: ["net:localhost:4455"],
    facts: [
      ["Versión", "1.0.0"],
      ["Licencia", "MIT"],
      ["Necesita Nyx", "1.0.0 o posterior"],
    ],
    news: ["1.0.0 — Primera versión."],
    featured: true,
    since: "1.0.0",
  },
  {
    id: "tepnyx.spotify",
    name: "Spotify",
    author: "Tepnyx",
    signed: true,
    category: "Música",
    price: "Gratis",
    short:
      "Pon la canción, el artista, el disco o la lista que digas, añade a la cola, guarda en favoritas y aleatorio o repetir.",
    long: "Pone exactamente lo que pides en Spotify, añade a la cola, guarda la canción que suena en tus favoritas, te dice qué suena y activa el aleatorio o la repetición. Pausar, seguir y pasar de canción los hace Nyx siempre, con cualquier app de música, sin instalar nada.",
    says: [
      "Pon mi lista de estudio",
      "Pon Bohemian Rhapsody en Spotify",
      "Añade esta a la cola",
      "Guárdala en favoritas",
      "Activa el aleatorio",
    ],
    needs: [
      "Spotify Premium (Spotify no deja poner música desde otras apps sin él)",
      "Una app tuya en developer.spotify.com (gratis, se hace una vez)",
    ],
    setup: [
      {
        auto: false,
        text: "Crea tu app de Spotify",
        detail:
          "En developer.spotify.com/dashboard, «Create app», con la dirección http://127.0.0.1/callback. Pídele a Nyx «¿cómo conecto Spotify?» y te guía paso a paso.",
      },
      {
        auto: false,
        text: "Pega su Client ID en Nyx",
        detail:
          "En Instaladas → Spotify. El «Client secret» no hace falta: nunca se lo des a nadie.",
      },
      {
        auto: true,
        text: "Iniciar sesión",
        detail: "Di «conecta Spotify»: Nyx abre el navegador, entras y te avisa al terminar.",
      },
    ],
    permissions: [
      "net:api.spotify.com:443",
      "net:accounts.spotify.com:443",
      "secrets",
      "notify",
      "apps:launch",
    ],
    facts: [
      ["Versión", "1.0.0"],
      ["Licencia", "MIT"],
      ["Necesita Nyx", "1.0.0 o posterior"],
    ],
    news: ["1.0.0 — Primera versión."],
    featured: true,
    since: "1.0.0",
  },
];
