# Aislamiento de extensiones con código (7.05)

Generado con `scripts/sandbox_probe.py` el 2026-11-14 en Windows 10.0.26300, 16 hilos. Python embeddable oficial 3.12.10. Todas las formas, dentro de un objeto de trabajo con: memoria 256 MB, 1 proceso, prioridad por debajo de lo normal, CPU 3 % del equipo (tope duro) y todas las restricciones de interfaz.

| Prueba | Sin aislar | Baja integridad | AppContainer | AppContainer + escritorio aparte | LPAC + escritorio aparte |
| --- | --- | --- | --- | --- | --- |
| Python funciona (ssl, sqlite3, ctypes, asyncio) | **sí** (['ssl', 'sqlite3', 'ctypes', 'asyncio']) | **sí** (['ssl', 'sqlite3', 'ctypes', 'asyncio']) | **sí** (['ssl', 'sqlite3', 'ctypes', 'asyncio']) | **sí** (['ssl', 'sqlite3', 'ctypes', 'asyncio']) | — |
| Leer un archivo del usuario | **sí** (17) | **sí** (17) | no (PermissionError: [Errno 13] Permission denied: '%USERPROFILE%\\AppData\\Local\\Temp\\claude\\fd618c45280a99d8\\368537) | no (PermissionError: [Errno 13] Permission denied: '%USERPROFILE%\\AppData\\Local\\Temp\\claude\\fd618c45280a99d8\\368537) | — |
| Ver qué hay en Documentos | **sí** (24) | **sí** (24) | no (PermissionError: [WinError 5] Acceso denegado: '%USERPROFILE%\\Documents') | no (PermissionError: [WinError 5] Acceso denegado: '%USERPROFILE%\\Documents') | — |
| Escribir fuera de su carpeta | **sí** (escrito) | no (PermissionError: [Errno 13] Permission denied: '%USERPROFILE%\\AppData\\Local\\Temp\\claude\\fd618c45280a99d8\\368537) | no (PermissionError: [Errno 13] Permission denied: '%USERPROFILE%\\AppData\\Local\\Temp\\claude\\fd618c45280a99d8\\368537) | no (PermissionError: [Errno 13] Permission denied: '%USERPROFILE%\\AppData\\Local\\Temp\\claude\\fd618c45280a99d8\\368537) | — |
| Escribir en su carpeta | **sí** (escrito) | **sí** (escrito) | **sí** (escrito) | **sí** (escrito) | — |
| Conectar a internet (1.1.1.1:443) | **sí** (conectado) | **sí** (conectado) | no (PermissionError: [WinError 10013] Intento de acceso a un socket no permitido por sus permisos de acceso) | no (PermissionError: [WinError 10013] Intento de acceso a un socket no permitido por sus permisos de acceso) | — |
| Resolver nombres (DNS) | **sí** (172.66.147.243) | **sí** (172.66.147.243) | no (gaierror: [Errno 11001] getaddrinfo failed) | no (gaierror: [Errno 11001] getaddrinfo failed) | — |
| Conectar a un servidor del propio PC | **sí** (conectado) | **sí** (conectado) | no (TimeoutError: timed out) | no (TimeoutError: timed out) | — |
| Leer el registro del usuario | **sí** (abierta) | **sí** (abierta) | **sí** (abierta) | **sí** (abierta) | — |
| Ver la lista de documentos recientes (registro) | **sí** (151 valores (no se leen)) | **sí** (151 valores (no se leen)) | **sí** (151 valores (no se leen)) | **sí** (151 valores (no se leen)) | — |
| Escribir en el registro del usuario | **sí** (creada) | no (PermissionError: [WinError 5] Acceso denegado) | no (PermissionError: [WinError 5] Acceso denegado) | no (PermissionError: [WinError 5] Acceso denegado) | — |
| Lanzar otro programa (cmd) | no (OSError: [WinError 1816] Cuota insuficiente para procesar este comando) | no (OSError: [WinError 1816] Cuota insuficiente para procesar este comando) | no (OSError: [WinError 1816] Cuota insuficiente para procesar este comando) | no (OSError: [WinError 1816] Cuota insuficiente para procesar este comando) | — |
| Abrir el portapapeles | **sí** (abierto (sin leerlo)) | **sí** (abierto (sin leerlo)) | no (OSError: [Errno 5] OpenClipboard) | no (OSError: [Errno 5] OpenClipboard) | — |
| Copiar la pantalla | **sí** (2560x1440, 8 colores distintos) | **sí** (2560x1440, 8 colores distintos) | **sí** (2560x1440, 8 colores distintos) | no (OSError: StretchBlt) | — |
| Leer el título de la ventana activa | no (OSError: [Errno 1400] sin título) | no (OSError: [Errno 1400] sin título) | no (OSError: [Errno 1400] sin título) | no (OSError: [Errno 1400] sin título) | — |
| Variables de entorno que ve | **sí** (['LOCALAPPDATA', 'PYTHONDONTWRITEBYTECODE', 'SYSTEMROOT', 'TEMP', 'TMP', 'USERPR) | **sí** (['LOCALAPPDATA', 'PYTHONDONTWRITEBYTECODE', 'SYSTEMROOT', 'TEMP', 'TMP', 'USERPR) | **sí** (['LOCALAPPDATA', 'PYTHONDONTWRITEBYTECODE', 'SYSTEMROOT', 'TEMP', 'TMP', 'USERPR) | **sí** (['LOCALAPPDATA', 'PYTHONDONTWRITEBYTECODE', 'SYSTEMROOT', 'TEMP', 'TMP', 'USERPR) | — |
| Reservar 512 MB (límite 256 MB) | no (MemoryError: ) | no (MemoryError: ) | no (MemoryError: ) | no (MemoryError: ) | — |
| CPU de un hilo en 2 s (tope 3 % del equipo) | **sí** (0.523) | **sí** (0.555) | **sí** (0.516) | **sí** (0.516) | — |
| Arranque hasta la 1.ª línea (mediana de 7) | 22 ms | 22 ms | 22 ms | 23 ms | None ms |
| Código de salida | 0x0 | 0x0 | 0x0 | 0x0 | 0xc0000022 |
| Pico de memoria de la sonda | 14.6 MB | 14.5 MB | 14.5 MB | 14.1 MB | 2.0 MB |

Salida suelta (normal):

```text
ready
```

Salida suelta (baja):

```text
ready
```

Salida suelta (appcontainer):

```text
ready
```

Salida suelta (appcontainer_escritorio):

```text
ready
```

## Qué dicen las medidas (escrito a mano, 2026-11-14)

- **Baja integridad no sirve:** solo impide escribir fuera de su carpeta y en el registro. Lee
  los archivos del usuario, ve sus Documentos, sale a internet y conecta con el propio PC.
- **AppContainer sin capacidades sí:** no lee ni escribe archivos del usuario, no tiene red
  (ni internet, ni DNS, ni el propio PC) y no puede escribir en el registro ni abrir el
  portapapeles. Python funciona entero (ssl, sqlite3, ctypes, asyncio) y arranca igual de
  rápido (22 ms hasta la primera línea, 14 MB).
- **Pero en el escritorio del usuario puede copiar la pantalla.** Con un **escritorio aparte**
  creado por Nyx (como hace Chromium con sus procesos), la copia falla: no ve las ventanas del
  usuario. Hay que dar permiso al contenedor sobre ese escritorio o `user32` no arranca.
- **Lo que queda abierto:** leer partes del registro del usuario que Windows abre a todas las
  apps (aquí, la lista de documentos recientes: 151 entradas) y los archivos del sistema. Sin
  red no lo puede sacar de su proceso; solo podría mandarlo a un servidor que tenga declarado
  con `net:`, y eso pasa por Nyx. **LPAC** (el AppContainer «menos privilegiado», que cerraría
  también el registro) no arrancó Python a la primera (`0xC0000022`, acceso denegado al
  cargar): se investiga en la 7.06.
- **El objeto de trabajo cumple:** 1 solo proceso (no puede lanzar otros), memoria con tope
  (512 MB con un límite de 256 MB: `MemoryError`), CPU con tope duro (3 % del equipo = 0,48 de
  un núcleo; medido 0,48–0,53) y sin acceso a ventanas de otros procesos ni al portapapeles.
- **Rareza encontrada:** si la carpeta del Python da permiso al SID del contenedor, ese mismo
  Python ya no arranca con baja integridad (`0xC0000135`). No afecta: se usa solo una forma.
- **Entorno:** CreateProcess pide `LOCALAPPDATA` y `USERPROFILE` en el entorno de un
  AppContainer (sin ellas, error 203) y los cambia por los del contenedor. El resto del entorno
  se pasa a mano: la extensión no ve `NYX_TOKEN` ni nada de Nyx.

## Propuesta para la 7.06

1. **AppContainer sin capacidades**, uno por extensión (`Tepnyx.Nyx.Ext.<id>`), en un
   **escritorio aparte** y dentro de un **objeto de trabajo**: 1 proceso, memoria por defecto
   512 MB, CPU con tope duro (10 % del equipo; 3 % en partida, cambiable en caliente),
   prioridad por debajo de lo normal (la mínima en partida), todas las restricciones de
   interfaz y matar al cerrar.
2. **Comunicación por la entrada y salida estándar** (JSON-RPC, una línea por mensaje), con las
   dos asas pasadas en una lista explícita (`PROC_THREAD_ATTRIBUTE_HANDLE_LIST`): nadie más
   puede conectarse y no hace falta dar permisos a una tubería con nombre. Cambia lo que decía
   HOJA-DE-RUTA §4.4 («tubería con nombre»).
3. **Permisos de carpetas:** el Python de las extensiones y el paquete, solo lectura; su
   carpeta de datos, lectura y escritura. Los `files:` y `net:` nunca se dan con permisos de
   Windows: los pide a Nyx, que comprueba el permiso aceptado y lo hace por ella.
4. **Python:** el «embeddable» oficial (PSF-2.0, firmado por la PSF), en la carpeta de Nyx. La
   3.12.10 es la última 3.12 con binarios (ahora solo hay parches en código fuente), así que al
   construir la 7.06 conviene la versión más nueva con binarios publicados y que las
   extensiones declaren para cuál traen sus dependencias.
5. **A investigar en la 7.06:** LPAC (cerraría el registro) y lo que tarda crear el escritorio y
   el contenedor al arrancar Nyx.
