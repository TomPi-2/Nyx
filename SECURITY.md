# Seguridad

Nyx actúa en tu PC: abre programas, mueve archivos, ejecuta comandos de PowerShell y lee webs.
Por eso la seguridad es una parte central del diseño (`docs/SPEC.md`, sección 8):

- Cada acción tiene un nivel de riesgo fijo (verde, amarillo o rojo) que decide **SafetyGuard
  con reglas**, nunca el modelo de lenguaje. Lo rojo siempre se confirma.
- Nunca se borra de forma permanente: todo va a la papelera y lo amarillo se puede deshacer.
- Lo que Nyx lee de fuera (webs, portapapeles, archivos) es información, nunca órdenes: tras
  leer una web, el modelo no tiene herramientas en esa vuelta.
- Todo funciona en local; a internet solo sale lo que la función necesita.

## Versiones con soporte

Mientras Nyx esté en desarrollo (versiones 0.x), solo la última versión publicada recibe
correcciones de seguridad.

## Cómo avisar de un fallo

**No abras una incidencia pública.** Usa el aviso privado de GitHub: pestaña *Security* del
repositorio → *Report a vulnerability*. Cuéntanos:

- Qué has encontrado y qué puede hacer alguien con ello.
- Cómo reproducirlo (la frase o el texto que lo provoca, la versión de Nyx y de Windows).
- Si se te ocurre, cómo arreglarlo.

Contestaremos en un plazo de 7 días y te diremos cuándo estará corregido. Si lo publicas, te
pedimos que esperes a que haya una versión corregida (o a 90 días desde tu aviso).

## Qué nos interesa especialmente

- Formas de que Nyx haga algo rojo **sin confirmación** o salte la lista de bloqueo de
  PowerShell (`core/nyx/tools/run_powershell.py`).
- Una web, un archivo o el portapapeles que consigan que Nyx **actúe** (inyección de órdenes).
- Borrado permanente, escritura fuera de las carpetas del usuario o en rutas protegidas.
- Acceso de otros programas o de la red al canal entre la interfaz y el núcleo (WebSocket
  local con token).
- Fugas de datos: audio, registros o el portapapeles saliendo del PC.
