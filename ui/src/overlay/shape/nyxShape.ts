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
  "uShade",
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
  private last = 0;
  private frameId = 0;
  private level = 0; // nivel de audio que llega del núcleo (0-1)
  private gray = 1; // 1 = blanco; menos = gris (fondo muy claro detrás)
  private grayTarget = 1;
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
    if (next === "thinking") s.merge.vel = -0.6;
    if (next === "speaking" && s.merge.v < 0.5) {
      s.flow.v = 1.0; // al juntarse se mece y se asienta
      s.flow.vel = 1.5;
    }
  }

  /** Nivel de audio (RMS del micro al escuchar, de la voz de Nyx al hablar). */
  setLevel(rms: number): void {
    this.level = Math.min(1, Math.max(0, rms * 4));
  }

  /** Luminancia (0-1) de lo que hay alrededor: blanco salvo sobre fondos muy claros. */
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
    const dt = Math.min(0.033, now - this.last);
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
    if (scale < 0.002) return; // nada que dibujar: la GPU descansa

    const phase = (this.clock / LOOP_S[state]) * Math.PI * 2;
    // Al esperar, gira con velocidad que sube y baja: al acelerar se endurece.
    const stiff = 0.5 + 0.5 * Math.sin(phase);
    const waiting = state === "waiting" || state === "hidden";
    const globalAngle = waiting ? phase / 4 - (0.75 * Math.cos(phase)) / 4 : (phase / 4) * 0.5;
    const cx = W / 2;
    const cy = H / 2;
    const listenPulse = state === "listening" ? 1 + 0.1 * s.audio.v : 1;
    const half = (this.size / 2) * dpr * scale * listenPulse;

    // Cuatro cuadrados: juntos forman el grande; separados orbitan y giran con esfuerzo.
    const m = Math.min(1.2, Math.max(-0.2, s.merge.v));
    const sep = 1 - Math.min(1, Math.max(0, m));
    const bursts = (phase / (Math.PI * 2)) * 3;
    const orbit = (effort(bursts) * (Math.PI / 2)) / 3;
    const subHalf = half * (0.5 - 0.12 * sep);
    const dist = half * (0.5 + 0.24 * sep) * Math.SQRT2;
    const boxes: number[] = [];
    for (let i = 0; i < 4; i++) {
      const base = Math.PI / 4 + (i * Math.PI) / 2 + globalAngle + orbit * sep;
      const wob = sep * 0.05 * Math.sin(phase * 2 + i * 1.7);
      const own = effort(bursts + i * 0.12) * (Math.PI / 2);
      boxes.push(
        cx + Math.cos(base) * dist * (1 + wob),
        cy + Math.sin(base) * dist * (1 + wob),
        subHalf,
        globalAngle + sep * own,
      );
    }
    const u = this.u;
    gl.uniform2f(u.uRes, W, H);
    gl.uniform4fv(u.uBox, new Float32Array(boxes));
    gl.uniform1f(u.uMerge, Math.min(1, Math.max(0, (m - 0.92) / 0.08)));
    gl.uniform4f(u.uBig, cx, cy, half, globalAngle);
    gl.uniform1f(u.uRound, state === "waiting" ? ROUND * (1.25 - 0.45 * stiff) : ROUND);
    gl.uniform1f(u.uK, half * (0.04 + 0.55 * Math.sin(Math.PI * Math.min(1, sep)) ** 2));
    const waitWobble = state === "waiting" ? 1.25 - 0.9 * stiff : 1;
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
    gl.uniform3f(u.uColor, g, g, g);
    gl.uniform1f(u.uShade, 1);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  };
}
