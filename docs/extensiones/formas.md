# Formas de Nyx: el contrato (tarea 7.09)

Una extensión de tipo `shape` cambia el aspecto de Nyx (la forma que aparece al llamarla). Es
un *fragment shader* GLSL que Nyx dibuja en su propia ventana. **No puede hacer daño:** no
tiene red, ni archivos, ni acceso a nada más que a los números que Nyx le pasa. La forma de
siempre es la extensión integrada `tepnyx.forma-nyx` y es la predeterminada.

## El paquete

```text
manifest.json     "kinds": ["shape"] (sin permisos: una forma no pide nada)
shape/shape.glsl  el shader (GLSL ES 1.00, máx. 32 KB)
shape/shape.json  {"name": "Gato", "box": 1.0}
```

- `box`: la caja máxima que puede ocupar la forma, en veces el tamaño elegido por el usuario
  (de 0,5 a 1,25). Nyx deja siempre 14 px entre esa caja y los paneles: lo que se dibuje fuera
  se recorta.

## El shader

Nyx antepone esto (no se escribe en el archivo, y el archivo no puede llevar `#version`,
`#extension` ni `#include`):

```glsl
precision mediump float;
uniform vec2  nyx_resolution; // tamaño del lienzo en px (la caja)
uniform float nyx_size;       // lado elegido por el usuario, en px (Ajustes → Apariencia)
uniform float nyx_time;       // segundos desde que apareció
uniform int   nyx_state;      // 0 reposo · 1 escucha · 2 piensa · 3 habla · 4 confirma · 5 error · 6 silenciada
uniform float nyx_audio;      // nivel de la voz (la del usuario al escuchar; la de Nyx al hablar), 0–1
uniform float nyx_phase;      // fase de un ciclo de 0 a 1 (para bucles sin saltos)
uniform float nyx_appear;     // 0 → 1 al aparecer, 1 → 0 al irse
uniform vec3  nyx_color;      // el color de Nyx elegido (Apariencia), en RGB lineal
```

Y espera que escriba `gl_FragColor` con **alfa premultiplicado** (transparente fuera de la
forma). Coordenadas: `gl_FragCoord.xy` en px, con el centro de la caja en
`nyx_resolution * 0.5`.

Reglas, comprobadas al instalar y al cargar:

- **GLSL ES 1.00**: los bucles tienen que tener un límite fijo, así que una forma no puede
  colgar la gráfica. Si no compila, Nyx usa la forma de siempre y Ajustes dice por qué.
- **Sin texturas** ni nada de fuera: solo los uniforms de arriba.
- **Coste**: se mide al cargar; si pasa de 2 ms por fotograma en la gráfica, se avisa. En
  partida Nyx no dibuja ninguna forma con cristal (SPEC §9 y §12), y la forma sigue igual de
  barata.
- Debe distinguir los estados por **brillo, tamaño y movimiento**, no por colores nuevos (SPEC
  §12: solo grises y el color que elija el usuario).

## Ejemplo mínimo

```glsl
void main() {
  vec2 p = gl_FragCoord.xy - nyx_resolution * 0.5;
  float r = nyx_size * 0.42 * nyx_appear * (1.0 + 0.08 * nyx_audio);
  float d = length(p) - r;                  // un círculo que late con la voz
  float a = clamp(0.5 - d, 0.0, 1.0);       // borde suave de 1 px
  gl_FragColor = vec4(nyx_color * a, a);
}
```
