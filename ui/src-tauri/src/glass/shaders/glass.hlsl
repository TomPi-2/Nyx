// Motor de cristal de Nyx (docs/INSTALADOR-Y-MOTOR-GRAFICO.md, apartado 2).
//
// Tres programas sobre un triángulo que cubre la ventana:
// - PSDown / PSUp: desenfoque Kawase doble (pocas pasadas a resolución reducida).
// - PSGlass: la lámina. Campo de distancia de rectángulos redondeados con el borde
//   ondulado por ruido (la misma técnica que la forma de Nyx), y a partir de ese campo
//   la cobertura, la refracción junto al borde, el brillo y la sombra.
//
// Coordenadas: píxeles físicos del área cliente de la ventana (SV_Position).

struct VSOut {
    float4 pos : SV_Position;
    float2 uv : TEXCOORD0;
};

VSOut VSMain(uint id : SV_VertexID) {
    VSOut o;
    float2 uv = float2((id << 1) & 2, id & 2);
    o.uv = uv;
    o.pos = float4(uv * float2(2.0, -2.0) + float2(-1.0, 1.0), 0.0, 1.0);
    return o;
}

SamplerState gLinear : register(s0);
Texture2D gSrc : register(t0);

// ---------------------------------------------------------------- desenfoque

cbuffer Blur : register(b0) {
    float2 gTexel;   // tamaño de un texel de la textura de origen (uv)
    float gOffset;   // separación de las muestras, en texels
    float gBlurPad;
};

float4 PSDown(VSOut i) : SV_Target {
    float2 o = gTexel * gOffset;
    float4 s = gSrc.SampleLevel(gLinear, i.uv, 0) * 4.0;
    s += gSrc.SampleLevel(gLinear, i.uv - o, 0);
    s += gSrc.SampleLevel(gLinear, i.uv + o, 0);
    s += gSrc.SampleLevel(gLinear, i.uv + float2(o.x, -o.y), 0);
    s += gSrc.SampleLevel(gLinear, i.uv - float2(o.x, -o.y), 0);
    return s / 8.0;
}

float4 PSUp(VSOut i) : SV_Target {
    float2 o = gTexel * gOffset;
    float4 s = gSrc.SampleLevel(gLinear, i.uv + float2(-2.0 * o.x, 0.0), 0);
    s += gSrc.SampleLevel(gLinear, i.uv + float2(-o.x, o.y), 0) * 2.0;
    s += gSrc.SampleLevel(gLinear, i.uv + float2(0.0, 2.0 * o.y), 0);
    s += gSrc.SampleLevel(gLinear, i.uv + float2(o.x, o.y), 0) * 2.0;
    s += gSrc.SampleLevel(gLinear, i.uv + float2(2.0 * o.x, 0.0), 0);
    s += gSrc.SampleLevel(gLinear, i.uv + float2(o.x, -o.y), 0) * 2.0;
    s += gSrc.SampleLevel(gLinear, i.uv + float2(0.0, -2.0 * o.y), 0);
    s += gSrc.SampleLevel(gLinear, i.uv + float2(-o.x, -o.y), 0) * 2.0;
    return s / 12.0;
}

// ---------------------------------------------------------------- lámina

#define MODE_TINT 0      // Bajo: tinte, sin mirar lo de detrás
#define MODE_BLUR 1      // Medio: desenfoque + tinte + brillo sencillo
#define MODE_GLASS 2     // Alto: + refracción en el borde + brillo especular
#define MAX_SHAPES 8

cbuffer Glass : register(b0) {
    float2 gSize;        // tamaño de la ventana (px)
    float2 gLoop;        // (cos, sin) de la fase del bucle: ruido periódico sin cortes
    float gAmp;          // amplitud del borde líquido (px)
    float gWave;         // longitud de onda del ruido (px)
    uint gMode;
    uint gCount;
    float4 gTint;        // rgb + opacidad
    float gRefraction;   // desplazamiento máximo junto al borde (px)
    float gBand;         // ancho de la franja que refracta (px)
    float gSpecular;
    float gGrain;
    float gSaturation;
    float gShadow;
    float gScale;        // píxeles físicos por píxel CSS
    float gSheen;
    float gSeed;
    float3 gGlassPad;
    float4 gRects[MAX_SHAPES];   // centro (xy) y semitamaño (zw), px
    float4 gParams[MAX_SHAPES];  // radio de esquina, amplitud relativa, -, -
};

// Ruido simplex 3D de Ashima Arts (MIT), el mismo que la forma de Nyx.
float3 mod289(float3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
float4 mod289(float4 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
float4 permute(float4 x) { return mod289(((x * 34.0) + 1.0) * x); }
float4 taylorInvSqrt(float4 r) { return 1.79284291400159 - 0.85373472095314 * r; }

float snoise(float3 v) {
    const float2 C = float2(1.0 / 6.0, 1.0 / 3.0);
    const float4 D = float4(0.0, 0.5, 1.0, 2.0);
    float3 i = floor(v + dot(v, C.yyy));
    float3 x0 = v - i + dot(i, C.xxx);
    float3 g = step(x0.yzx, x0.xyz);
    float3 l = 1.0 - g;
    float3 i1 = min(g.xyz, l.zxy);
    float3 i2 = max(g.xyz, l.zxy);
    float3 x1 = x0 - i1 + C.xxx;
    float3 x2 = x0 - i2 + C.yyy;
    float3 x3 = x0 - D.yyy;
    i = mod289(i);
    float4 p = permute(permute(permute(i.z + float4(0.0, i1.z, i2.z, 1.0)) + i.y
        + float4(0.0, i1.y, i2.y, 1.0)) + i.x + float4(0.0, i1.x, i2.x, 1.0));
    float n_ = 0.142857142857;
    float3 ns = n_ * D.wyz - D.xzx;
    float4 j = p - 49.0 * floor(p * ns.z * ns.z);
    float4 x_ = floor(j * ns.z);
    float4 y_ = floor(j - 7.0 * x_);
    float4 x = x_ * ns.x + ns.yyyy;
    float4 y = y_ * ns.x + ns.yyyy;
    float4 h = 1.0 - abs(x) - abs(y);
    float4 b0 = float4(x.xy, y.xy);
    float4 b1 = float4(x.zw, y.zw);
    float4 s0 = floor(b0) * 2.0 + 1.0;
    float4 s1 = floor(b1) * 2.0 + 1.0;
    float4 sh = -step(h, float4(0.0, 0.0, 0.0, 0.0));
    float4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
    float4 a1 = b1.xzyw + s1.xzyw * sh.zzww;
    float3 p0 = float3(a0.xy, h.x);
    float3 p1 = float3(a0.zw, h.y);
    float3 p2 = float3(a1.xy, h.z);
    float3 p3 = float3(a1.zw, h.w);
    float4 norm = taylorInvSqrt(float4(dot(p0, p0), dot(p1, p1), dot(p2, p2), dot(p3, p3)));
    p0 *= norm.x;
    p1 *= norm.y;
    p2 *= norm.z;
    p3 *= norm.w;
    float4 m = max(0.6 - float4(dot(x0, x0), dot(x1, x1), dot(x2, x2), dot(x3, x3)), 0.0);
    m = m * m;
    return 42.0 * dot(m * m, float4(dot(p0, x0), dot(p1, x1), dot(p2, x2), dot(p3, x3)));
}

float sdRoundRect(float2 p, float2 b, float r) {
    float2 q = abs(p) - b + r;
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
}

struct Nearest {
    float d;      // distancia sin ondular (negativa dentro)
    float wob;    // amplitud relativa de esa forma
    float4 rect;
};

Nearest nearest(float2 p) {
    Nearest n;
    n.d = 1e9;
    n.wob = 0.0;
    n.rect = gRects[0];
    for (uint k = 0; k < gCount; k++) {
        float4 r = gRects[k];
        float rad = min(gParams[k].x, min(r.z, r.w));
        float d = sdRoundRect(p - r.xy, r.zw, rad);
        if (d < n.d) {
            n.d = d;
            n.wob = gParams[k].y;
            n.rect = r;
        }
    }
    return n;
}

// Ondulación del borde: ondas amplias y lentas (nada de rizos pequeños).
float wobble(float2 p) {
    float2 u = p / gWave;
    float n = snoise(float3(u + gLoop * 0.45, gSeed));
    n += 0.18 * snoise(float3(u * 1.6 - gLoop * 0.35, gSeed + 7.0));
    return n;
}

float field(float2 p) {
    Nearest n = nearest(p);
    float amp = gAmp * n.wob;
    return amp > 0.0 ? n.d + amp * wobble(p) : n.d;
}

float hash(float2 p) {
    return frac(sin(dot(p, float2(12.9898, 78.233))) * 43758.5453);
}

float4 PSGlass(VSOut i) : SV_Target {
    float2 p = i.pos.xy;
    Nearest n = nearest(p);
    float amp = gAmp * n.wob;
    float reach = amp * 1.25 + 1.0;
    float shadowOffset = 6.0 * gScale;
    float shadowReach = 30.0 * gScale;

    // Lejos de todas las formas: transparente (la mayor parte de la ventana).
    if (n.d > reach + shadowReach + shadowOffset) {
        return float4(0.0, 0.0, 0.0, 0.0);
    }

    // El ruido y el gradiente solo se calculan cerca del borde: dentro y lejos no cambian nada.
    bool edge = n.d > -(reach + gBand);
    float d = (edge && amp > 0.0) ? n.d + amp * wobble(p) : n.d;
    float cov = saturate(0.5 - d);

    // Sombra suave y desplazada hacia abajo: la única separación del fondo (sin bordes).
    float shadow = 0.0;
    if (gShadow > 0.0 && cov < 1.0) {
        float ds = max(nearest(p - float2(0.0, shadowOffset)).d, 0.0);
        shadow = gShadow * 0.28 * exp(-ds / (11.0 * gScale)) * saturate(1.0 - ds / shadowReach);
    }
    if (cov <= 0.0) {
        return float4(0.0, 0.0, 0.0, shadow);
    }

    // Normal 2D (hacia fuera) y franja del borde, a partir del mismo campo.
    float2 nrm = float2(0.0, 0.0);
    float rim = 0.0;
    float edgeLine = 0.0;
    if (edge) {
        const float e = 1.0;
        float2 g = float2(field(p + float2(e, 0.0)) - field(p - float2(e, 0.0)),
                          field(p + float2(0.0, e)) - field(p - float2(0.0, e)));
        nrm = g / max(length(g), 1e-4);
        rim = saturate(1.0 + d / gBand);
        edgeLine = saturate(1.0 + d / (2.5 * gScale));
    }

    float2 rel = (p - (n.rect.xy - n.rect.zw)) / max(2.0 * n.rect.zw, float2(1.0, 1.0));
    float3 col;
    float alpha;
    if (gMode == MODE_TINT) {
        col = gTint.rgb;
        alpha = gTint.a;
    } else {
        // La imagen se dobla hacia dentro junto al borde, como una lente.
        float2 off = gMode == MODE_GLASS ? -nrm * gRefraction * rim * rim : float2(0.0, 0.0);
        float2 uv = clamp((p + off) / gSize, 0.0, 1.0);
        col = gSrc.SampleLevel(gLinear, uv, 0).rgb;
        float l = dot(col, float3(0.2126, 0.7152, 0.0722));
        col = lerp(l.xxx, col, gSaturation);
        col = lerp(col, gTint.rgb, gTint.a);
        alpha = 1.0;
    }

    // Brillo: degradado suave desde arriba.
    col += gSheen * (1.0 - smoothstep(0.0, 0.6, rel.y));

    if (gMode == MODE_GLASS && edge) {
        // Luz desde arriba a la izquierda: línea fina en el borde y un halo más ancho.
        float2 L = float2(-0.55, -0.83);
        float lit = pow(saturate(dot(nrm, L)), 3.0) + 0.45 * pow(saturate(dot(nrm, -L)), 3.0);
        col += gSpecular * lit * (edgeLine + 0.35 * rim * rim);
    }

    // Grano fino y fijo (no cambia con el tiempo: no parpadea).
    col += (hash(floor(p)) - 0.5) * gGrain;
    col = saturate(col);

    float a = alpha * cov;
    return float4(col * a, a + shadow * (1.0 - a));
}
