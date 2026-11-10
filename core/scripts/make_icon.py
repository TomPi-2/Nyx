r"""Genera el icono de Nyx (propuesta D · Sólido, aprobada el 2026-11-10).

Misma geometría que la forma de Nyx (ui/src/overlay/shape/shaders.ts): cuadrado redondeado
(42 %·0,40) deformado con ruido simplex de baja frecuencia, en un instante fijo. Se dibuja con
numpy y supermuestreo (8×8) para que los bordes salgan suaves también a 16 px.

    uv run python scripts/make_icon.py
Sale en ui/src-tauri/icons/:
  - source/nyx-1024.png     icono de la app (blanco con un volumen sutil y una sombra suave
                            para verse también sobre fondos claros) → `npm run tauri icon`
  - tray-dark.png           bandeja con barra de tareas oscura (blanco)
  - tray-light.png          bandeja con barra de tareas clara (gris oscuro)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ICONS = Path(__file__).resolve().parents[2] / "ui" / "src-tauri" / "icons"
# D · Sólido (los mismos números que en el prototipo del icono).
AMP, FREQ, PHASE, ROUND, SEED = 0.06, 0.5, 0.4, 0.40, 3.7
HALF = 0.36  # semilado / tamaño del lienzo


# --- Ruido simplex 3D (Ashima Arts, MIT), vectorizado: misma fórmula que el shader ---
def _mod289(x: np.ndarray) -> np.ndarray:
    return x - np.floor(x * (1.0 / 289.0)) * 289.0


def _permute(x: np.ndarray) -> np.ndarray:
    return _mod289(((x * 34.0) + 1.0) * x)


def snoise(v: np.ndarray) -> np.ndarray:
    """v: (..., 3) → (...)"""
    c = np.array([1.0 / 6.0, 1.0 / 3.0])
    i = np.floor(v + np.sum(v, -1, keepdims=True) * c[1])
    x0 = v - i + np.sum(i, -1, keepdims=True) * c[0]
    g = (x0[..., [1, 2, 0]] <= x0).astype(float)  # step(x0.yzx, x0.xyz)
    lo = 1.0 - g
    i1 = np.minimum(g, lo[..., [2, 0, 1]])
    i2 = np.maximum(g, lo[..., [2, 0, 1]])
    x1 = x0 - i1 + c[0]
    x2 = x0 - i2 + c[1]
    x3 = x0 - 0.5
    i = _mod289(i)

    def corners(axis: int) -> np.ndarray:
        """vec4(0, i1.k, i2.k, 1) para el eje k (como en el shader)."""
        zero = np.zeros_like(i1[..., axis])
        return np.stack([zero, i1[..., axis], i2[..., axis], zero + 1.0], -1)

    p = _permute(i[..., 2:3] + corners(2))
    p = _permute(p + i[..., 1:2] + corners(1))
    p = _permute(p + i[..., 0:1] + corners(0))
    n_ = 0.142857142857
    ns = n_ * np.array([2.0, 0.5, 1.0]) - np.array([0.0, 1.0, 0.0])  # D.wyz - D.xzx
    j = p - 49.0 * np.floor(p * ns[2] * ns[2])
    x_ = np.floor(j * ns[2])
    y_ = np.floor(j - 7.0 * x_)
    x = x_ * ns[0] + ns[1]
    y = y_ * ns[0] + ns[1]
    h = 1.0 - np.abs(x) - np.abs(y)
    b0 = np.stack([x[..., 0], x[..., 1], y[..., 0], y[..., 1]], -1)
    b1 = np.stack([x[..., 2], x[..., 3], y[..., 2], y[..., 3]], -1)
    s0 = np.floor(b0) * 2.0 + 1.0
    s1 = np.floor(b1) * 2.0 + 1.0
    sh = -(h <= 0.0).astype(float)  # -step(h, 0)
    a0 = b0[..., [0, 2, 1, 3]] + s0[..., [0, 2, 1, 3]] * sh[..., [0, 0, 1, 1]]
    a1 = b1[..., [0, 2, 1, 3]] + s1[..., [0, 2, 1, 3]] * sh[..., [2, 2, 3, 3]]
    p0 = np.stack([a0[..., 0], a0[..., 1], h[..., 0]], -1)
    p1 = np.stack([a0[..., 2], a0[..., 3], h[..., 1]], -1)
    p2 = np.stack([a1[..., 0], a1[..., 1], h[..., 2]], -1)
    p3 = np.stack([a1[..., 2], a1[..., 3], h[..., 3]], -1)
    dots = np.stack([np.sum(q * q, -1) for q in (p0, p1, p2, p3)], -1)
    norm = 1.79284291400159 - 0.85373472095314 * dots
    p0, p1, p2, p3 = (q * norm[..., k : k + 1] for k, q in enumerate((p0, p1, p2, p3)))
    m = np.maximum(0.6 - np.stack([np.sum(q * q, -1) for q in (x0, x1, x2, x3)], -1), 0.0)
    m = m * m
    pd = np.stack([np.sum(a * b, -1) for a, b in ((p0, x0), (p1, x1), (p2, x2), (p3, x3))], -1)
    return 42.0 * np.sum(m * m * pd, -1)


def field(px: np.ndarray, py: np.ndarray, size: float) -> np.ndarray:
    """Distancia (en píxeles) al borde de la forma; negativa dentro."""
    h = HALF * size
    cx = cy = size / 2
    qx, qy = np.abs(px - cx), np.abs(py - cy)
    r = h * ROUND
    ax, ay = qx - h + r, qy - h + r
    d = np.hypot(np.maximum(ax, 0), np.maximum(ay, 0)) + np.minimum(np.maximum(ax, ay), 0) - r
    ux, uy = (px - cx) / h, (py - cy) / h
    lx, ly = np.cos(PHASE), np.sin(PHASE)
    v1 = np.stack([ux * FREQ + lx * 0.45, uy * FREQ + ly * 0.45, np.full_like(ux, SEED)], -1)
    v2 = np.stack(
        [ux * FREQ * 1.6 - lx * 0.35, uy * FREQ * 1.6 - ly * 0.35, np.full_like(ux, SEED + 7)], -1
    )
    n = snoise(v1) + 0.18 * snoise(v2)
    return d + AMP * h * n


def render(size: int, gray: float, *, shade: bool, ss: int = 8) -> Image.Image:
    """RGBA de `size`×`size`: la forma en `gray` (1 = blanco) con supermuestreo `ss`×`ss`."""
    big = size * ss
    ys, xs = np.mgrid[0:big, 0:big].astype(np.float64)
    px, py = (xs + 0.5) / ss, (ys + 0.5) / ss  # coordenadas en píxeles del icono final
    d = field(px, py, size) * ss  # distancia en píxeles de la imagen grande
    alpha = np.clip(0.5 - d, 0, 1)
    col = np.full_like(alpha, gray)
    if shade:  # el mismo volumen sutil que la forma
        e = 1.5 / ss
        gx = (field(px + e, py, size) - field(px - e, py, size)) * ss
        gy = (field(px, py + e, size) - field(px, py - e, size)) * ss
        nz = 2.2 * 1.5
        ln = np.sqrt(gx * gx + gy * gy + nz * nz)
        nx, ny, nzz = -gx / ln, -gy / ln, nz / ln
        lv = np.array([-0.45, -0.6, 0.65]) / np.linalg.norm([-0.45, -0.6, 0.65])
        light = nx * lv[0] + ny * lv[1] + nzz * lv[2]
        rim = 1 - np.clip(-d / (HALF * size * ss * 0.22), 0, 1) ** 2 * (
            3 - 2 * np.clip(-d / (HALF * size * ss * 0.22), 0, 1)
        )
        # Solo cerca del borde: en el interior el ruido dejaba una mancha gris en el centro.
        col = gray * (1 - rim * (0.07 - 0.035 * light))
    rgba = np.stack([col, col, col, alpha], -1)
    rgba = rgba.reshape(size, ss, size, ss, 4)
    a = rgba[..., 3].mean(axis=(1, 3))
    rgb = (rgba[..., :3] * rgba[..., 3:4]).sum(axis=(1, 3)) / np.maximum(
        rgba[..., 3:4].sum(axis=(1, 3)), 1e-9
    )
    out = np.concatenate([np.clip(rgb, 0, 1), a[..., None]], -1)
    return Image.fromarray((out * 255 + 0.5).astype(np.uint8), "RGBA")


def with_shadow(icon: Image.Image) -> Image.Image:
    """Sombra muy difusa debajo (solo para el icono de la app: se ve sobre fondos blancos)."""
    size = icon.width
    shadow = Image.new("RGBA", icon.size, (0, 0, 0, 0))
    alpha = icon.getchannel("A").point(lambda v: int(v * 0.42))
    dark = Image.new("RGBA", icon.size, (0, 0, 0, 255))
    dark.putalpha(alpha)
    shadow.alpha_composite(dark, (0, int(size * 0.025)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(size * 0.03))
    shadow.alpha_composite(icon)
    return shadow


def main() -> int:
    (ICONS / "source").mkdir(parents=True, exist_ok=True)
    app = with_shadow(render(1024, 1.0, shade=True, ss=2))
    app.save(ICONS / "source" / "nyx-1024.png")
    render(64, 1.0, shade=False).save(ICONS / "tray-dark.png")
    render(64, 0.24, shade=False).save(ICONS / "tray-light.png")
    print(f"Iconos en {ICONS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
