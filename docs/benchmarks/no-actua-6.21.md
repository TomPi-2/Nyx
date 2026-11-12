# Que el modelo actúe (tarea 6.21) · 2026-11-12

Batería de 337 frases (`scripts/battery.py`), PC de referencia (RX 7700 XT), 3 pasadas por
frase del LLM salvo donde se indica. Línea base de la 6.17: **256/337** (LLM 110/185).

| Prueba | Acierto | LLM | Primer token (mediana / media) |
| --- | --- | --- | --- |
| Nyx tras la 6.20b (qwen2.5:7b, todas las herramientas) | 258/337 | 112/185 | 350 / 358 ms |
| **Paso 1: orden escrita como texto → router** (lo que queda en Nyx) | **262/337** | **116/185** | 355 / 381 ms |
| Paso 1 + paso 2 (aviso de «se resuelve con herramientas» en el mensaje) | 259/337 | 113/185 | 366 / 394 ms |
| qwen3:4b-instruct (1 pasada; prompt afinado para qwen2.5) | 220/337 | 74/185 | 272 / 317 ms |

Informe completo del paso 1 en `bateria-6.21.md` (nueva línea base).

## Qué dice

- **El paso 1 ayuda (+4) sin coste:** cuando el 7B escribe la orden en vez de llamar a la
  herramienta («pon el volumen al 100», sin cabecera y corta), el router la entiende y se
  ejecuta. Pasa por SafetyGuard como cualquier llamada y nunca en el bucle de agente (lo que
  acaba de leer de fuera no puede volverse una orden).
- **El paso 2 no ayuda:** el aviso en el mensaje no hace que el 7B consulte. Sigue narrando
  lo que haría («Veré cuánto espacio libre tienes», «Systeminfo {"what": "battery"}») o
  inventándose el dato («Estás escuchando "Shape of You" de Ed Sheeran»). Queda en el código
  desactivado (`Brain(tools_hint=…)`, `battery.py --con-aviso`) para medirlo con otros
  modelos. El paso 3 (la misma regla en el prompt de sistema) no se prueba: es decirle lo
  mismo en otro sitio, y cambiar el prompt de sistema mueve otras frases.
- **Es un límite del modelo**, así que toca el paso 4 (otro modelo, aprobado el 2026-11-12).
  Primer intento, qwen3:4b-instruct (Apache-2.0, ya estaba en el plan como alternativa):
  **peor** (74/185, mismo fallo) y además **5 veces más lento al generar** en este PC
  (15 tokens/s frente a 70 del qwen2.5:7b, todo en la gráfica): el backend Vulkan de Ollama
  no rinde igual con la arquitectura qwen3. Descartado.
