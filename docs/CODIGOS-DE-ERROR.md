# Códigos de error de Nyx

Cuando algo falla, Nyx (o su instalador) enseña un código como **I-110** junto al aviso. Con
él se busca aquí qué ha pasado y qué hacer. Este archivo es la fuente de la página
`tepnyx.com/nyx/errores` (cada código, con su ancla: `#I-110`).

Formato: una letra por la parte de Nyx y tres cifras. **I**: instalador. **D**: descargas
del primer arranque (modelos, Ollama y el cerebro). **A**: actualizaciones. **N**: el núcleo
de Nyx (lo que escucha, piensa y actúa).

Al añadir un código: aquí, en el sitio donde se produce (con el mismo número) y en la web.
Los números no se reutilizan aunque un error deje de existir.

## I · Instalador

| Código | Qué ha pasado | Qué hacer |
| --- | --- | --- |
| I-101 | No se ha podido descargar Nyx (sin conexión, o GitHub no responde). | Comprueba la conexión y pulsa «Reintentar». Si sigue, descarga «Instalar Nyx» otra vez de la web. |
| I-102 | Lo descargado no coincide con su huella SHA-256: podría estar dañado o alterado, así que no se usa. | Pulsa «Reintentar». Si se repite, avisa: no instales esa versión. |
| I-103 | La versión publicada no trae la huella de su instalador. | Es un fallo de la publicación: avisa y prueba más tarde. |
| I-110 | El instalador de la app (Velopack) ha terminado con error. | Pulsa «Reintentar». El detalle está en `%LOCALAPPDATA%\Velopack\velopack.log`. |
| I-111 | La app parece instalada pero no aparece `Nyx.exe` en `%LOCALAPPDATA%\TepnyxNyx`. | Pulsa «Reintentar». Si sigue, mira si un antivirus lo ha puesto en cuarentena. |
| I-112 | No se ha podido abrir el instalador de la app. | Mira si un antivirus lo bloquea y pulsa «Reintentar». |
| I-113 | Ya hay una Nyx instalada y algo tiene abierta su carpeta (`%LOCALAPPDATA%\TepnyxNyx`), así que no se puede sustituir. El instalador ya ha cerrado Ollama y Everything y lo ha reintentado. | Cierra las ventanas del Explorador o terminales que estén en esa carpeta y pulsa «Reintentar». Si sigue, reinicia el PC y vuelve a abrir el instalador. |
| I-120 | No se ha podido guardar lo elegido en «Opciones» (`%APPDATA%\Nyx\instalador.json`). | Nyx funciona igual; Everything se puede instalar luego desde Ajustes → Caché. |
| I-121 | No se ha podido poner «Arrancar con Windows». | Nyx funciona igual; ábrela desde el menú Inicio. |
| I-122 | No se ha podido crear el acceso directo del escritorio. | Nyx está en el menú Inicio y en la bandeja. |
| I-130 | No se ha podido preparar el oído y la voz (el núcleo de Nyx no arranca). | Pulsa «Reintentar». Si sigue, abre Nyx: lo bajará ella en su panel de descargas. |
| I-131 | Alguna descarga del oído o la voz ha fallado (cada una se reintenta cinco veces y sigue donde se cortó). | Abre Nyx: reintenta sola lo que falte, donde lo dejó. El motivo queda en `%LOCALAPPDATA%\Nyx\logs\instalador.log`. |
| I-140 | Nyx está instalada pero no se ha podido abrir. | Ábrela desde el menú Inicio. |

## D · Descargas del primer arranque

| Código | Qué ha pasado | Qué hacer |
| --- | --- | --- |
| D-201 | No se ha podido descargar una parte del oído o la voz (sin conexión o el servidor no responde). | «Reintentar» en el panel de descargas: sigue donde iba. |
| D-202 | Una descarga no coincide con su huella SHA-256: no se usa. | «Reintentar». Si se repite, avisa. |
| D-210 | No se ha podido instalar Ollama (falta winget o ha fallado). | Instala Ollama desde ollama.com y pulsa «Reintentar». |
| D-211 | Ollama está instalado pero no responde. | Abre Ollama desde el menú Inicio y pulsa «Reintentar». |
| D-220 | Ollama no ha podido bajar el cerebro de Nyx. | Comprueba la conexión y el espacio libre (unos 5 GB) y pulsa «Reintentar». |

## A · Actualizaciones

| Código | Qué ha pasado | Qué hacer |
| --- | --- | --- |
| A-301 | No se ha podido mirar si hay versión nueva. | Nada: lo vuelve a intentar en unas horas. |
| A-302 | No se ha podido descargar la versión nueva. | Nada: lo vuelve a intentar en unas horas. |
| A-303 | No se ha podido aplicar la versión nueva. | Nyx sigue con la que tenías. Si se repite, descarga «Instalar Nyx» de la web. |
| A-304 | La versión nueva no arrancaba bien y Nyx ha vuelto sola a la anterior. | Nada: sigue funcionando. Cuando salga un arreglo, se actualizará sola. |

## N · Núcleo

| Código | Qué ha pasado | Qué hacer |
| --- | --- | --- |
| N-401 | El núcleo de Nyx se ha cerrado tres veces seguidas al arrancar. | Bandeja → «Reiniciar». Si sigue, el detalle está en `%LOCALAPPDATA%\Nyx\logs\core.log`. |
| N-402 | No se ha podido lanzar el núcleo de Nyx (falta o un antivirus lo bloquea). | Reinstala Nyx con «Instalar Nyx» (tus datos se quedan). |
