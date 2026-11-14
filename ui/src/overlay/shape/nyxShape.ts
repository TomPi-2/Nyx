/**
 * La forma de Nyx (SPEC sección 12): cuadrado redondeado blanco que se comporta como un
 * líquido-sólido. Portado del prototipo aprobado (docs/prototipos/forma-nyx-v2.html) con
 * sus valores: fluidez 1, velocidad 1, redondez 42 %.
 *
 * Es un campo de distancia (SDF) en un shader: cuatro cuadrados unidos con unión suave (los
 * puentes de líquido al dividirse o juntarse) y deformados con ruido de baja frecuencia.
 * Todos los bucles dependen de una fase que da la vuelta completa: no se nota el corte.
 */

import { FRAGMENT, VERTEX } from "./shaders";

export type ShapeState = "hidden" | "waiting" | "listening" | "thinking" | "speaking";

/** Lienzo = tamaño × esto: sitio para deformarse, girar y separarse en cuatro. */
export const SHAPE_PAD = 1.8;

const BURST_S = 1.6; // un empujón de los cuatro al pensar (3 por bucle de 4,8 s, como el prototipo)
const FLOW = 1;
const SPEED = 1;
const ROUND = 0.42;
const LOOP_S: Record<ShapeState, number> = {
  hidden: 6,
  waiting: 6,
  listening: 6,
  thinking: 4.8,
  speaking: 6,
};
const FLOW_BY_STATE: Record<ShapeState, number> = {
  hidden: 0.4,
  waiting: 0.55,
  listening: 0.35,
  thinking: 0.4,
  speaking: 0.3,
};
const UNIFORMS = [
  "uRes",
  "uBox",
  "uMerge",
  "uBig",
  "uRound",
  "uK",
  "uAmp",
  "uFreq",
  "uLoop",
  "uSeed",
  "uAudio",
  "uTime",
  "uSquash",
  "uColor",
  "uFill",
  "uEmpty",
] as const;

/** Muelle crítico-amortiguado sencillo: el valor va hacia su objetivo con algo de rebote. */
class Spring {
  v: number;
  t: number;
  vel = 0;
  constructor(
    v: number,
    private k = 120,
    private c = 14,
  ) {
    this.v = v;
    this.t = v;
  }
  step(dt: number): number {
    const f = this.k * (this.t - this.v) - this.c * this.vel;
    this.vel += f * dt;
    this.v += this.vel * dt;
    return this.v;
  }
}

/** Un cuarto de vuelta: con este giro, los cuatro (y cada cuadrado) se ven igual. */
const QUARTER = Math.PI / 2;

/** Siguiente múltiplo de 90° hacia delante (o el mismo, si ya lo es). */
function forwardQuarter(x: number): number {
  return Math.ceil(x / QUARTER - 1e-4) * QUARTER;
}

function isQuarter(x: number): boolean {
  return Math.abs(x / QUARTER - Math.round(x / QUARTER)) < 1e-3;
}

/**
 * Al dejar de pensar, los cuatro se acercan hasta casi tocarse (MERGE_HOLD) sin fundirse.
 * Cada giro avanza (nunca retrocede) hasta el siguiente cuarto de vuelta con un empujón
 * propio, más largo cuanto más le falte, y solo entonces se funden en un cuadrado.
 */
const MERGE_HOLD = 0.84; // separación casi cerrada mientras termina de girar (uMerge funde > 0,92)
const MERGE_MIN_S = 0.45; // duración del último giro: mínimo…
const MERGE_PER_QUARTER_S = 0.75; // …más esto por cada cuarto de vuelta que falte

/** Al juntarse: giros al empezar, dónde terminan y el reloj del último empujón. */
interface Merging {
  orbit: number;
  own: number[];
  orbitTo: number;
  ownTo: number[];
  start: number;
  duration: number;
  fused: boolean;
}

/** Acelera y frena sin tirones (la misma curva que los empujones al pensar). */
function ease(p: number): number {
  const e = Math.min(1, Math.max(0, p));
  return e * e * e * (e * (e * 6 - 15) + 10);
}

/** Empujón con esfuerzo: acelera y frena (78 % del tramo) y descansa el resto. */
function effort(x: number): number {
  const k = Math.floor(x);
  const f = x - k;
  const e = f < 0.78 ? f / 0.78 : 1;
  return k + e * e * e * (e * (e * 6 - 15) + 10);
}

export class NyxShape {
  private gl: WebGLRenderingContext;
  private u = {} as Record<(typeof UNIFORMS)[number], WebGLUniformLocation | null>;
  private state: ShapeState = "hidden";
  private stateSince = 0;
  private clock = 0;
  private angle = 0; // giro continuo del conjunto
  private rate = 0; // su velocidad (rad/s), que cambia con suavidad entre estados
  private waitMix = 0; // 1 = espera (matices de fluido no newtoniano), 0 = otros estados
  private thinkClock = 0; // tiempo pensando (los giros de los cuatro cuentan desde aquí)
  // Giros de los cuatro al pensar: el de la órbita y el propio de cada uno (rad). Se
  // acumulan mientras piensa; al juntarse terminan en el siguiente múltiplo de 90° hacia
  // delante (los cuatro y cada cuadrado se ven igual cada cuarto de vuelta), así que la
  // unión nunca deshace las vueltas dadas.
  private orbitTerm = 0;
  private ownTerm = [0, 0, 0, 0];
  private orbitFrom = 0;
  private ownFrom = [0, 0, 0, 0];
  private merging: Merging | null = null;
  private last = 0;
  private frameId = 0;
  /** Fotogramas por segundo como mucho (0 = los de la pantalla). En partida, 30. */
  maxFps = 0;
  private level = 0; // nivel de audio que llega del núcleo (0-1)
  private gray = 1; // 1 = blanco; menos = gris (fondo muy claro detrás)
  private grayTarget = 1;
  /** Color elegido en Apariencia (0–1); blanco por defecto. */
  private color: [number, number, number] = [1, 1, 1];
  /** El instalador (9.08): sin girar (los bordes siguen vivos). La isla siempre gira. */
  spin = true;
  /** El instalador: se llena como un vaso hasta este nivel (0–1); null = entera. */
  private fill: number | null = null;
  private fillShown = 0;
  /** Lo que aún no está lleno: este color y opacidad (0–1). */
  private empty: [number, number, number, number] = [0.5, 0.5, 0.52, 0.28];
  private readonly s = {
    scale: new Spring(0, 90, 9), // aparición con rebote
    merge: new Spring(1, 60, 11), // 1 = un cuadrado, 0 = cuatro
    flow: new Spring(0.5, 40, 9), // cuánto se deforma
    audio: new Spring(0, 260, 24),
    squash: new Spring(0, 200, 16),
  };

  /** `size`: lado del cuadrado en píxeles CSS (ajustable en Apariencia). */
  constructor(
    private canvas: HTMLCanvasElement,
    public size = 100,
    private reduceMotion = matchMedia("(prefers-reduced-motion: reduce)"),
  ) {
    const gl = canvas.getContext("webgl", { premultipliedAlpha: true, antialias: false });
    if (!gl) throw new Error("WebGL no disponible");
    this.gl = gl;
    const prog = gl.createProgram()!;
    gl.attachShader(prog, this.compile(gl.VERTEX_SHADER, VERTEX));
    gl.attachShader(prog, this.compile(gl.FRAGMENT_SHADER, FRAGMENT));
    gl.linkProgram(prog);
    gl.useProgram(prog);
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, "a");
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    for (const name of UNIFORMS) this.u[name] = gl.getUniformLocation(prog, name);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    this.last = performance.now() / 1000;
    this.frameId = requestAnimationFrame(this.frame);
  }

  private compile(type: number, src: string): WebGLShader {
    const gl = this.gl;
    const sh = gl.createShader(type)!;
    gl.shaderSource(sh, src);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
      throw new Error(gl.getShaderInfoLog(sh) ?? "shader");
    }
    return sh;
  }

  setState(next: ShapeState): void {
    if (next === this.state) return;
    const now = performance.now() / 1000;
    const wasThinking = this.state === "thinking";
    this.state = next;
    this.stateSince = now;
    const s = this.s;
    if (next === "hidden") {
      s.scale.t = 0;
    } else {
      if (s.scale.v < 0.05) {
        // Nace como una gota que salta y se asienta.
        s.scale.v = 0;
        s.scale.vel = 6.5;
        s.flow.v = 2.2;
      }
      s.scale.t = 1;
    }
    s.merge.t = next === "thinking" ? 0 : 1;
    if (next === "thinking" && !wasThinking) this.startThinking();
    if (wasThinking && next !== "thinking") this.startMerging();
    if (next === "thinking") s.merge.vel = -0.6;
    if (next === "speaking" && s.merge.v < 0.5) {
      s.flow.v = 1.0; // al juntarse se mece y se asienta
      s.flow.vel = 1.5;
    }
  }

  /** 0 = un solo cuadrado; 1 = los cuatro separados del todo. */
  private separation(): number {
    const m = Math.min(1.2, Math.max(-0.2, this.s.merge.v));
    return 1 - Math.min(1, Math.max(0, m));
  }

  /**
   * Empieza a pensar: los giros cuentan desde donde estén. Si estaba junto y alineado, se
   * parte de cero (a múltiplos de 90° se ve igual); si se vuelve a pensar a mitad de la
   * unión, se sigue desde ahí sin saltos.
   */
  private startThinking(): void {
    const aligned = isQuarter(this.orbitTerm) && this.ownTerm.every(isQuarter);
    if (this.separation() < 0.02 && aligned) {
      this.orbitTerm = 0;
      this.ownTerm = [0, 0, 0, 0];
    }
    this.orbitFrom = this.orbitTerm;
    this.ownFrom = [...this.ownTerm];
    this.merging = null;
    this.thinkClock = 0;
  }

  /** Deja de pensar: cada giro irá hacia delante hasta el siguiente cuarto de vuelta. */
  private startMerging(): void {
    const orbitTo = forwardQuarter(this.orbitTerm);
    const ownTo = this.ownTerm.map(forwardQuarter);
    const left = Math.max(orbitTo - this.orbitTerm, ...ownTo.map((t, i) => t - this.ownTerm[i]));
    this.merging = {
      orbit: this.orbitTerm,
      own: [...this.ownTerm],
      orbitTo,
      ownTo,
      start: this.clock,
      duration: MERGE_MIN_S + (MERGE_PER_QUARTER_S * left) / QUARTER,
      fused: false,
    };
    // Se acercan, pero no se funden hasta terminar de girar (ver frame).
    this.s.merge.t = MERGE_HOLD;
  }

  /** Nivel de audio (RMS del micro al escuchar, de la voz de Nyx al hablar). */
  setLevel(rms: number): void {
    this.level = Math.min(1, Math.max(0, rms * 4));
  }

  /** Luminancia (0-1) de lo que hay alrededor: blanco salvo sobre fondos muy claros. */
  /** Color de la forma (Ajustes → Apariencia). Sobre fondos muy claros se oscurece igual
   * que el blanco pasa a gris, para seguir distinguiéndose. */
  setColor(rgb: [number, number, number]): void {
    this.color = rgb;
  }

  /** Llenarse hasta `level` (0–1) con un oleaje suave en la superficie; null = entera. */
  setFill(level: number | null, empty?: [number, number, number, number]): void {
    this.fill = level === null ? null : Math.min(1, Math.max(0, level));
    if (empty) this.empty = empty;
  }

  setBackdrop(luma: number): void {
    this.grayTarget = luma > 0.85 ? 0.62 : luma > 0.7 ? 0.86 : 1;
  }

  /** ¿Sigue visible? (para ocultar la ventana cuando termina de desaparecer). */
  get visible(): boolean {
    return this.state !== "hidden" || this.s.scale.v > 0.01;
  }

  destroy(): void {
    cancelAnimationFrame(this.frameId);
  }

  private frame = (): void => {
    this.frameId = requestAnimationFrame(this.frame);
    const now = performance.now() / 1000;
    // Con un tope (en partida), se salta el fotograma si aún no toca: medio margen para no
    // perder uno de cada dos por redondeo.
    if (this.maxFps > 0 && now - this.last < 0.5 / this.maxFps + 0.5 / 60) return;
    const dt = Math.min(0.05, now - this.last);
    this.last = now;
    const speed = SPEED * (this.reduceMotion.matches ? 0.35 : 1);
    this.clock += dt * speed;
    const s = this.s;
    const state = this.state;

    const voiced = state === "listening" || state === "speaking";
    s.audio.t = voiced ? this.level : 0;
    s.flow.t = FLOW_BY_STATE[state] * FLOW;
    s.squash.t = state === "speaking" ? this.level : 0;
    for (const sp of Object.values(s)) sp.step(dt);
    // Al desaparecer, el muelle se para en seco al llegar a cero: si no, rebota y asoma un
    // cuadradito blanco durante un instante después de haberse ido.
    if (state === "hidden" && s.scale.v <= 0.001) {
      s.scale.v = 0;
      s.scale.vel = 0;
    }
    this.gray += (this.grayTarget - this.gray) * Math.min(1, dt * 4);

    const gl = this.gl;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const W = Math.round(this.canvas.clientWidth * dpr);
    const H = Math.round(this.canvas.clientHeight * dpr);
    if (this.canvas.width !== W || this.canvas.height !== H) {
      this.canvas.width = W;
      this.canvas.height = H;
      gl.viewport(0, 0, W, H);
    }
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    const scale = Math.max(0, s.scale.v);
    // La unión termina aunque no se dibuje (si se oculta mientras gira, que no quede a medias
    // y se funda al volver a aparecer).
    const merging = this.merging;
    if (merging && !merging.fused && this.clock - merging.start >= merging.duration) {
      merging.fused = true;
      s.merge.t = 1;
    }
    if (scale < 0.002) return; // nada que dibujar: la GPU descansa

    // Una sola fase para todos los estados: cambiar de estado no hace saltar el ruido.
    const phase = (this.clock / LOOP_S.waiting) * Math.PI * 2;
    // Al esperar, gira con velocidad que sube y baja: al acelerar se endurece. El giro es un
    // ángulo continuo (solo cambia su velocidad, con suavidad): pasar de espera a escucha no
    // lo hace saltar. En un bucle de espera da justo un cuarto de vuelta (la media del seno
    // es cero), así que tampoco se nota el corte.
    const stiff = 0.5 + 0.5 * Math.sin(phase);
    const quarterPerLoop = Math.PI / 2 / LOOP_S.waiting;
    const waitingNow = state === "waiting";
    const rateTarget = waitingNow
      ? quarterPerLoop * (1 + 0.75 * Math.sin(phase))
      : quarterPerLoop * 0.5;
    this.rate += (rateTarget - this.rate) * Math.min(1, dt * 3);
    this.angle += this.rate * dt * speed * (this.spin ? 1 : 0);
    this.waitMix += ((waitingNow ? 1 : 0) - this.waitMix) * Math.min(1, dt * 4);
    const globalAngle = this.angle;
    // Al pensar, los giros cuentan desde que empezó a pensar (si no, al separarse recorrían
    // de golpe todo el ángulo acumulado desde que arrancó Nyx).
    if (state === "thinking") this.thinkClock += dt * speed;
    const cx = W / 2;
    const cy = H / 2;
    const listenPulse = state === "listening" ? 1 + 0.1 * s.audio.v : 1;
    const half = (this.size / 2) * dpr * scale * listenPulse;

    // Cuatro cuadrados: juntos forman el grande; separados orbitan y giran con esfuerzo.
    const m = Math.min(1.2, Math.max(-0.2, s.merge.v));
    const sep = 1 - Math.min(1, Math.max(0, m));
    const bursts = this.thinkClock / BURST_S;
    if (state === "thinking") {
      // Orbitan y giran con esfuerzo desde donde empezaron a pensar.
      const orbit = (effort(bursts) * QUARTER) / 3;
      this.orbitTerm = this.orbitFrom + orbit * sep;
      for (let i = 0; i < 4; i++) {
        const own = (effort(bursts + i * 0.12) - effort(i * 0.12)) * QUARTER;
        this.ownTerm[i] = this.ownFrom[i] + own * sep;
      }
    } else if (this.merging) {
      // El último giro hacia delante, con su propio empujón; al acabar, se funden.
      const g = this.merging;
      const k = ease((this.clock - g.start) / g.duration);
      this.orbitTerm = g.orbit + (g.orbitTo - g.orbit) * k;
      for (let i = 0; i < 4; i++) this.ownTerm[i] = g.own[i] + (g.ownTo[i] - g.own[i]) * k;
      if (k >= 1 && !g.fused) {
        g.fused = true;
        s.merge.t = 1;
      }
    }
    const subHalf = half * (0.5 - 0.12 * sep);
    const dist = half * (0.5 + 0.24 * sep) * Math.SQRT2;
    const boxes: number[] = [];
    for (let i = 0; i < 4; i++) {
      const base = Math.PI / 4 + i * QUARTER + globalAngle + this.orbitTerm;
      const wob = sep * 0.05 * Math.sin(phase * 2 + i * 1.7);
      boxes.push(
        cx + Math.cos(base) * dist * (1 + wob),
        cy + Math.sin(base) * dist * (1 + wob),
        subHalf,
        globalAngle + this.ownTerm[i],
      );
    }
    const u = this.u;
    gl.uniform2f(u.uRes, W, H);
    gl.uniform4fv(u.uBox, new Float32Array(boxes));
    gl.uniform1f(u.uMerge, Math.min(1, Math.max(0, (m - 0.92) / 0.08)));
    gl.uniform4f(u.uBig, cx, cy, half, globalAngle);
    // Los matices de la espera (redondez y ondas que cambian con el giro) entran y salen poco
    // a poco, para que el paso a escucha sea continuo.
    gl.uniform1f(u.uRound, ROUND * (1 + this.waitMix * (0.25 - 0.45 * stiff)));
    gl.uniform1f(u.uK, half * (0.04 + 0.55 * Math.sin(Math.PI * Math.min(1, sep)) ** 2));
    const waitWobble = 1 + this.waitMix * (0.25 - 0.9 * stiff);
    gl.uniform1f(u.uAmp, half * 0.15 * Math.max(0, s.flow.v) * waitWobble);
    gl.uniform1f(u.uFreq, 0.55 + 0.25 * sep);
    gl.uniform2f(u.uLoop, Math.cos(phase), Math.sin(phase));
    gl.uniform1f(u.uSeed, 3.7);
    gl.uniform1f(
      u.uAudio,
      state === "listening" ? s.audio.v : state === "speaking" ? s.audio.v * 0.55 : 0,
    );
    gl.uniform1f(u.uTime, this.clock);
    const sq = Math.max(0, s.squash.v);
    gl.uniform2f(u.uSquash, 1 + 0.06 * sq, 1 - 0.11 * sq);
    const g = this.gray;
    const [cr, cg, cb] = this.color;
    gl.uniform3f(u.uColor, cr * g, cg * g, cb * g);
    // Lleno hasta un nivel (instalador): la línea sube con suavidad, en píxeles del lienzo.
    if (this.fill !== null) {
      this.fillShown += (this.fill - this.fillShown) * Math.min(1, dt * 4);
      gl.uniform1f(u.uFill, cy + half - 2 * half * this.fillShown);
    } else {
      gl.uniform1f(u.uFill, -1e6);
    }
    gl.uniform4f(u.uEmpty, ...this.empty);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  };
}
