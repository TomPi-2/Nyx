// Shaders de la forma de Nyx (copiados del prototipo aprobado, docs/prototipos/forma-nyx-v2.html).
// Ruido simplex 3D de Ashima Arts (MIT).

export const VERTEX = `attribute vec2 a; void main(){ gl_Position = vec4(a, 0.0, 1.0); }`;

export const FRAGMENT = `
precision highp float;
uniform vec2 uRes;
uniform vec4 uBox[4];      // centro (px), semilado (px), ángulo
uniform float uMerge;      // 1 = un solo cuadrado, 0 = cuatro
uniform vec4 uBig;         // cuadrado entero: centro, semilado, ángulo
uniform float uRound;      // radio de esquina / semilado
uniform float uK;          // unión suave (px): puentes de líquido
uniform float uAmp;        // amplitud del ruido (px)
uniform float uFreq;       // frecuencia del ruido (por semilado)
uniform vec2 uLoop;        // (cos, sin) de la fase del bucle: ruido periódico
uniform float uSeed;
uniform float uAudio;      // nivel de voz (0-1)
uniform float uTime;
uniform vec2 uSquash;      // estirar/aplastar al hablar
uniform vec3 uColor;
uniform float uFill;       // instalador: altura (px) del nivel; por encima, uEmpty (-1e6 = entera)
uniform vec4 uEmpty;       // color y opacidad de lo que aún no está lleno

// Ruido simplex 3D (Ashima Arts, MIT)
vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
float snoise(vec3 v){
  const vec2 C=vec2(1.0/6.0,1.0/3.0); const vec4 D=vec4(0.0,0.5,1.0,2.0);
  vec3 i=floor(v+dot(v,C.yyy)); vec3 x0=v-i+dot(i,C.xxx);
  vec3 g=step(x0.yzx,x0.xyz); vec3 l=1.0-g; vec3 i1=min(g.xyz,l.zxy); vec3 i2=max(g.xyz,l.zxy);
  vec3 x1=x0-i1+C.xxx; vec3 x2=x0-i2+C.yyy; vec3 x3=x0-D.yyy;
  i=mod289(i);
  vec4 p=permute(permute(permute(i.z+vec4(0.0,i1.z,i2.z,1.0))+i.y+vec4(0.0,i1.y,i2.y,1.0))+i.x+vec4(0.0,i1.x,i2.x,1.0));
  float n_=0.142857142857; vec3 ns=n_*D.wyz-D.xzx;
  vec4 j=p-49.0*floor(p*ns.z*ns.z); vec4 x_=floor(j*ns.z); vec4 y_=floor(j-7.0*x_);
  vec4 x=x_*ns.x+ns.yyyy; vec4 y=y_*ns.x+ns.yyyy; vec4 h=1.0-abs(x)-abs(y);
  vec4 b0=vec4(x.xy,y.xy); vec4 b1=vec4(x.zw,y.zw);
  vec4 s0=floor(b0)*2.0+1.0; vec4 s1=floor(b1)*2.0+1.0; vec4 sh=-step(h,vec4(0.0));
  vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy; vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
  vec3 p0=vec3(a0.xy,h.x); vec3 p1=vec3(a0.zw,h.y); vec3 p2=vec3(a1.xy,h.z); vec3 p3=vec3(a1.zw,h.w);
  vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
  p0*=norm.x; p1*=norm.y; p2*=norm.z; p3*=norm.w;
  vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0); m=m*m;
  return 42.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
}
float sdRoundBox(vec2 p, float b, float r){ vec2 q=abs(p)-vec2(b)+r; return length(max(q,0.0))+min(max(q.x,q.y),0.0)-r; }
float smin(float a,float b,float k){ float h=clamp(0.5+0.5*(b-a)/k,0.0,1.0); return mix(b,a,h)-k*h*(1.0-h); }
mat2 rot(float a){ float c=cos(a), s=sin(a); return mat2(c,-s,s,c); }

float boxAt(vec2 p, vec4 b){
  vec2 q = rot(-b.w) * (p - b.xy);
  q /= uSquash;
  return sdRoundBox(q, b.z, b.z*uRound) * min(uSquash.x, uSquash.y);
}
float field(vec2 p){
  float d4 = boxAt(p, uBox[0]);
  for (int i=1;i<4;i++) d4 = smin(d4, boxAt(p, uBox[i]), uK);
  float d1 = boxAt(p, uBig);
  float d = mix(d4, d1, uMerge);
  // Superficie viva: ruido periódico (la fase recorre un círculo: el bucle no tiene corte).
  vec2 c = uBig.xy; float h = max(uBig.z, 1.0);
  vec2 u = (p - c) / h;
  // Ondas amplias y profundas (una sola octava de baja frecuencia: nada de rizos pequeños).
  float n = snoise(vec3(u*uFreq + uLoop*0.45, uSeed));
  n += 0.18*snoise(vec3(u*uFreq*1.6 - uLoop*0.35, uSeed+7.0));
  d += uAmp * n;
  // La voz mueve la superficie con lóbulos grandes (aquí no hace falta bucle: va con el sonido).
  float a = atan(u.y, u.x);
  d -= uAudio * h * 0.11 * (0.55 + 0.45*sin(a*2.0 + uTime*3.2)) * (0.6 + 0.4*snoise(vec3(u*0.9, uTime*1.1)));
  return d;
}
void main(){
  vec2 p = gl_FragCoord.xy; p.y = uRes.y - p.y;
  float d = field(p);
  float alpha = clamp(0.5 - d, 0.0, 1.0);
  if (alpha <= 0.0) { gl_FragColor = vec4(0.0); return; }
  // Color plano: todo el cuadrado exactamente del color elegido (6.23). El sombreado de antes
  // (borde un 7 % más oscuro y una luz según la pendiente) partía la forma en cuatro triángulos
  // por las diagonales, que con colores se notaban; y calculaba la forma 5 veces por píxel.
  // Llena como un vaso (instalador, 9.08): por encima del nivel, el color de «vacío», con un
  // oleaje suave en la superficie.
  float level = uFill + 3.0 * sin(p.x * 0.06 + uTime * 2.4) + 2.0 * sin(p.x * 0.11 - uTime * 1.7);
  float full = clamp(p.y - level + 0.5, 0.0, 1.0);
  vec4 filled = vec4(uColor * alpha, alpha);
  vec4 empty = vec4(uEmpty.rgb * uEmpty.a * alpha, uEmpty.a * alpha);
  gl_FragColor = mix(empty, filled, full);
}
`;
