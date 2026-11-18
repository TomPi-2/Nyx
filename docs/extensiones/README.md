# Extensiones de Nyx: guía para desarrolladores

Una extensión añade a Nyx cosas que no trae: herramientas nuevas (controlar OBS o Spotify),
atajos para una app, conocimiento que puede consultar, preajustes, una personalidad o una
forma nueva. Se instala desde Ajustes → Extensiones y se puede desactivar o quitar sin
reiniciar.

Esta guía es para quien las hace. El kit (`sdk/` y `core/scripts/nyx_ext.py`) tiene licencia
MIT: tu extensión puede tener la licencia que quieras.

**Contenido**

1. Cómo empezar
2. Qué hay en un paquete
3. El manifiesto
4. Herramientas con código
5. Lo que una extensión puede pedir a Nyx
6. Permisos
7. Ajustes que pone el usuario
8. Extensiones sin código
9. Probar
10. Buenas prácticas
11. Firmar y publicar
12. Límites
13. Ejemplos

## 1. Cómo empezar

Necesitas Windows 11, Nyx y, para las herramientas con código, Python 3.12 o posterior en tu
equipo para probar (dentro de Nyx tu código corre con el Python 3.14 de Nyx). De momento el kit
está en el repositorio de Nyx: desde `core/`, con `uv`.

```powershell
uv run python scripts/nyx_ext.py new ..\mi-extension --id tunombre.saludos --tipo tools
uv run python scripts/nyx_ext.py validate ..\mi-extension
uv run python scripts/nyx_ext.py run ..\mi-extension saluda --args '{"nombre": "Ana"}'
uv run python scripts/nyx_ext.py pack ..\mi-extension
```

- `new` crea una extensión de ejemplo que funciona. Tipos: `tools`, `actions`, `knowledge`,
  `preset`, `personality` y `shape`. Nunca sobrescribe nada.
- `validate` la comprueba como lo hace Nyx al instalarla.
- `run` ejecuta una herramienta **como en Nyx**: encerrada, con los permisos del manifiesto y
  con lo que pida a Nyx de verdad (red, avisos…). `--ajuste clave=valor` le da sus ajustes, y
  `--sin-aislar` la corre con tu Python para depurar (solo con tu propio código).
- `pack` crea el `.nyxext` sin las pruebas ni las cachés.

Para instalarla sin firmar, activa **Ajustes → Extensiones → Modo desarrollador** y elige el
`.nyxext` en «Desde un archivo». Saldrá con la etiqueta «Sin revisar».

## 2. Qué hay en un paquete

Un `.nyxext` es un zip con esta forma (solo lo que uses):

```text
manifest.json          obligatorio
tools/main.py          herramientas con código (y tools/lib/ para tus dependencias)
tools/tools.json       su descripción para Nyx
actions.json           atajos de teclado por app
knowledge/*.md         lo que Nyx puede consultar
presets/*.json         preajustes
personality.json       personalidad
shape/shape.json       forma de Nyx (y shape/shape.glsl)
signature              la firma de Tepnyx (la pone Tepnyx al revisarla)
```

Nyx rechaza paquetes con rutas que salen de su carpeta, enlaces, nombres que Windows trata
de forma especial (`con`, `aux`, `nombre.`, `archivo:flujo`), nombres repetidos con otras
mayúsculas, o que parezcan una zip bomba.

## 3. El manifiesto

```json
{
  "id": "tunombre.obs-extra",
  "name": "OBS extra",
  "version": "1.0.0",
  "author": "Tu nombre",
  "description": "Lo que hace, en una frase.",
  "nyx_api": ">=1.0 <2.0",
  "kinds": ["tools", "knowledge"],
  "permissions": ["net:localhost:4455", "notify"],
  "groups": [
    {
      "name": "obs_extra",
      "about": "Filtros y transiciones de OBS",
      "keywords": ["obs", "filtro", "transicion"],
      "tools": ["obs_filter"]
    }
  ],
  "game_policy": { "obs_filter": "allowed" },
  "settings": [{ "key": "password", "label": "Contraseña de OBS" }],
  "license": { "type": "free", "spdx": "MIT" },
  "homepage": "https://ejemplo.com"
}
```

| Campo | Qué es |
| --- | --- |
| `id` | `autor.nombre` en minúsculas (letras, números y guiones). No cambia nunca. |
| `version` | SemVer `MAYOR.MENOR.PARCHE`. Nyx no deja instalar una versión más vieja. |
| `nyx_api` | Las versiones de la API de Nyx con las que funciona: `1.0`, `>=1.0`, `>=1.0 <2.0`. |
| `kinds` | `tools`, `actions`, `knowledge`, `preset`, `personality`, `shape` (y `mode`, aún sin uso). |
| `permissions` | Lo que pide (sección 6). Solo las de `tools`: lo demás no ejecuta nada. |
| `groups` | Cómo encuentra Nyx tus herramientas (sección 10). Solo con `tools`. |
| `game_policy` | Si una herramienta puede usarse en partida; manda sobre `tools.json`. |
| `settings` | Lo que el usuario tiene que darle a mano (sección 7). |
| `license` | `free`, o `paid` con `product` (de pago único, nunca suscripción). `spdx`, la licencia del código. |
| `homepage` | Solo `https://`. |

Campos de más, permisos inventados o mal escritos: no se instala, y Nyx dice por qué.

## 4. Herramientas con código

Cada herramienta es una función de Python marcada con `@nyx.tool` en `tools/main.py`:

```python
import nyx


@nyx.tool
async def obs_filter(fuente: str, filtro: str, activar: bool) -> str:
    sock = await nyx.ask("ws.open", {"url": "ws://localhost:4455"})
    ...
    return f"Filtro «{filtro}» activado en «{fuente}»."
```

- Puede ser `async` (recomendado) o normal; las normales corren en otro hilo y usan
  `nyx.ask_sync`.
- Lo que devuelve, Nyx se lo dice al usuario: un texto, o un objeto con `message` (lo que
  dice), `display` (lo que enseña en la burbuja), `secondary` (una segunda línea) y `speak`.
- Si algo no se puede hacer, lanza `nyx.Error("OBS no está abierto")`: Nyx lo enseña tal cual.
  Otra excepción sale como un fallo, con su tipo, y su traza va al registro de Nyx.
- `print` no rompe nada: va al registro de Nyx.
- `nyx.data_dir` es tu carpeta de datos, la única donde puedes escribir por tu cuenta.

Nyx tiene que conocerlas sin arrancar tu código, así que se describen en `tools/tools.json`:

```json
[
  {
    "name": "obs_filter",
    "description": "Activa o quita un filtro de una fuente de OBS.",
    "parameters": {
      "properties": {
        "fuente": { "type": "string", "description": "La fuente, como la diga el usuario" },
        "filtro": { "type": "string" },
        "activar": { "type": "boolean" }
      },
      "required": ["fuente", "filtro", "activar"]
    },
    "risk": "green",
    "uses": ["net:localhost:4455"],
    "game_policy": "allowed"
  }
]
```

- `name`: minúsculas, números y `_`, igual que la función. Un prefijo propio (`obs_…`) evita
  choques: si otra herramienta ya se llama así, la tuya no se carga.
- `parameters`: `string`, `integer`, `number` o `boolean`, con `description` y, si quieres,
  `enum`. Nada más: así el modelo de Nyx se equivoca menos.
- `risk`: `green` (lo hace sin preguntar), `yellow` (lo hace y avisa con «deshacer»), `red`
  (pregunta antes). Nyx usa **el mayor** entre el que declaras y el mínimo de los permisos que
  dices usar en `uses` (sin `uses`, el de todos tus permisos). Algo que se ve en público, cuesta
  dinero o no se puede deshacer va en `red`.
- `game_policy`: `allowed` (también en partida), `deferred` («te lo hago al terminar», por
  defecto) o `blocked`. Una roja en partida espera siempre al final, salvo en modo normal.

Cómo corre tu código: un proceso por extensión, en un AppContainer de Windows sin
capacidades, en su propio escritorio, con 512 MB de memoria y un 10 % del procesador (un 3 %
en partida). No tiene red, no ve tus archivos ni la pantalla y no puede abrir programas: lo
que necesite se lo pide a Nyx. Arranca la primera vez que se usa (unos 0,1 s) y se para tras
10 minutos sin uso. Cada llamada tiene 20 s; si no contesta, se para. Si se cae tres veces
seguidas, Nyx la desactiva y avisa.

Tus dependencias van en `tools/lib/` (Python puro, o ruedas para Windows y Python 3.14).

## 5. Lo que una extensión puede pedir a Nyx

`await nyx.ask(método, datos, timeout_s=30)`. Si Nyx dice que no (sin permiso, dirección no
válida, el servicio no contesta…), lanza `RuntimeError` con el motivo.

| Método | Datos | Devuelve | Permiso |
| --- | --- | --- | --- |
| `net.fetch` | `url`, `method` (GET, POST, PUT, PATCH, DELETE), `headers`, `body` (texto), `timeout_s` (≤ 30) | `{status, headers, body}` (1 MB como mucho; sin seguir redirecciones) | `net:<servidor>:<puerto>` |
| `ws.open` | `url` (`ws://` o `wss://`) | un número de conexión (4 a la vez) | `net:<servidor>:<puerto>` |
| `ws.send` | `id`, `text` | — | (el de `ws.open`) |
| `ws.recv` | `id`, `timeout_s` (≤ 30) | el texto, o `null` si no llega nada a tiempo | (el de `ws.open`) |
| `ws.close` | `id` | — | — |
| `secrets.get` / `.set` / `.delete` | `key`, (`value`) | el valor o `null` | `secrets` |
| `settings.get` | `key` | lo que puso el usuario o `null` | ninguno (solo los de tu manifiesto) |
| `oauth.authorize` | `authorize_url`, `token_url`, `client_id`, `scopes`, `timeout_s` (≤ 300) | `{access_token, refresh_token, expires_in, scope, token_type}` | `net:` de las dos direcciones |
| `open.uri` | `uri` | — | `apps:launch` |
| `notify` | `title`, `text` | — | `notify` |
| `clipboard.read` / `.write` | (`text`) | el texto | `clipboard:read` / `clipboard:write` |
| `files.list` / `.read` | `folder`, `path` | lista, o `{text}` / `{base64}` (1 MB) | `files:read:<carpeta>` |
| `files.write` | `folder`, `path`, `text` o `base64` | — | `files:write:<carpeta>` |
| `apps.open` | `name` («Spotify») | lo que ha hecho | `apps:launch` |
| `audio.volume` | `level` (0–100), `change` (−100…100) o `mute` | lo que ha hecho | `audio` |
| `media.control` | `action` (`play`, `pause`, `play_pause`, `next`, `previous`, `stop`), (`source`) | lo que ha hecho | `media` |
| `media.playing` | — | qué suena | `media` |
| `ui.panel` | `title`, `text` y/o `sections` (`[{title, items, ordered}]`, 6 × 20) | — | `ui:panel` |
| `llm.ask` | `prompt` (≤ 4.000), (`system`) | la respuesta | `llm` |
| `apps.window` | `app`, `action` (`focus`, `minimize`, `maximize`, `restore`, `close`) | lo que ha hecho | `apps:control:<app>` |
| `apps.action` | `app`, `action` (las acciones de Nyx: `save`, `new_tab`…), (`times`) | lo que ha hecho | `apps:control:<app>` |
| `apps.keys` | `app`, `keys` («ctrl+l») | lo que ha hecho | `apps:control:<app>` |

- **Secretos**: cada extensión ve solo los suyos, en el Administrador de credenciales de
  Windows. Al desinstalarla se borran.
- **Iniciar sesión** (`oauth.authorize`): OAuth 2 con PKCE. Nyx abre el navegador, escucha la
  vuelta en `http://127.0.0.1:<puerto libre>/callback` y cambia el código por los tokens. Tu
  código nunca ve la contraseña. Registra en el servicio la dirección `http://127.0.0.1/callback`
  si deja puerto libre (Spotify sí). No funciona en partida. Como el usuario puede tardar, no lo
  esperes dentro de la herramienta: lánzalo en segundo plano (`asyncio.create_task`), contesta
  «te abro el navegador» y avisa con `notify` al terminar (lo hace la extensión de Spotify).
- **Abrir** (`open.uri`): la app por su esquema (de momento solo `spotify:`; pide otros a
  Tepnyx) o tus webs (`https://` a servidores de tus permisos). Nunca `file:`, ni
  `ms-settings:`, ni programas sueltos.
- **Archivos**: carpetas por nombre (`documentos`, `descargas`, `escritorio`, `imagenes`,
  `musica`, `videos`), nunca rutas libres. Lo que `files.write` sustituye va a la papelera.
- **Apps, volumen y música** (`apps.open`, `audio.volume`, `media.*`): Nyx lo hace con sus
  propias herramientas, igual que si se lo pidiera el usuario, y te devuelve lo que ha hecho.
- **Controlar una app** (`apps.window`, `apps.action`, `apps.keys`): solo la app de tu
  permiso (`apps:control:spotify` → `"app": "spotify"`) y nunca en partida. Las teclas pasan
  por el mismo filtro que las de Nyx.
- **El cerebro de Nyx** (`llm.ask`): una pregunta suelta, sin herramientas ni la conversación
  del usuario. 20 por hora y extensión; nunca en partida (la gráfica es del juego).
- **Paneles** (`ui.panel`): el panel largo de Nyx, con texto o secciones (una lista, unos
  pasos).
- **Mensajes**: no hay método. Con `messages:<servicio>` envías con tu propia red y Nyx sube
  tus herramientas a rojo: pregunta al usuario antes de cada envío.

No existe nada para pulsar teclas en un juego, leer su memoria ni inyectarse en otro programa,
y no existirá.

## 6. Permisos

El usuario los ve en palabras normales antes de instalar («Controlar OBS Studio», «Guardar
claves en el Administrador de credenciales»…). Si una actualización pide uno nuevo, sigue la
versión anterior hasta que lo acepte. Pide solo lo que uses.

| Permiso | Para qué | Riesgo mínimo |
| --- | --- | --- |
| `net:<servidor>:<puerto>` | conectar con ese servidor (p. ej. `net:localhost:4455`, `net:api.spotify.com:443`) | verde |
| `files:read:<carpeta>` / `files:write:<carpeta>` ★ | leer o guardar en una carpeta conocida | verde / amarillo |
| `apps:launch` | abrir apps y sus webs | verde |
| `apps:control:<app>` ★ | la ventana, los botones y los atajos de una app | amarillo |
| `audio`, `media` | volumen y multimedia | verde |
| `clipboard:read` ★, `clipboard:write` | portapapeles | verde |
| `notify` | avisos | verde |
| `ui:panel` | paneles de Nyx | verde |
| `secrets` | claves en el Administrador de credenciales | verde |
| `llm` ★ | usar el cerebro de Nyx | verde |
| `messages:<servicio>` ★ | mandar mensajes a otras personas | rojo |

`ui:widget` (1.1) y `screen` (1.2) aún no existen.

### Permisos delicados (★)

`files:write`, `clipboard:read`, `apps:control`, `llm` y `messages` necesitan la aprobación
de Tepnyx, que va dentro de la firma: sin ella, la extensión solo se instala con el modo
desarrollador. Cada uno lleva en el manifiesto su porqué, en `why` (de 10 a 300 caracteres),
que es lo que lee Tepnyx al revisarlo:

```json
"permissions": ["clipboard:read", "notify"],
"why": { "clipboard:read": "Traduce el texto que el usuario ha copiado cuando lo pide." }
```

Para pedirlos, sube el paquete a una dirección `https` y envía la solicitud (sección 11).

## 7. Ajustes que pone el usuario

Lo que el usuario tiene que darte a mano (una contraseña, un identificador de app) va en
`settings` del manifiesto:

```json
"settings": [
  { "key": "password", "label": "Contraseña de OBS", "hint": "Dónde encontrarla." },
  { "key": "client_id", "label": "Client ID", "secret": false }
]
```

Salen en Ajustes → Extensiones, en tu extensión. Se guardan en el Administrador de credenciales
y los lees con `nyx.ask("settings.get", {"key": "password"})`. Los secretos (`secret`, por
defecto `true`) no se vuelven a enseñar una vez guardados. Tu código no puede cambiarlos.
Léelos cada vez que los uses: el usuario puede cambiarlos en cualquier momento.

## 8. Extensiones sin código

No piden permisos ni ejecutan nada: solo se validan.

- **`actions.json`**: atajos de teclado por app, que Nyx usa con «guarda», «graba», «nueva
  pestaña»…

  ```json
  {
    "apps": [
      {
        "name": "Mi editor",
        "processes": ["mieditor.exe"],
        "names": ["mi editor", "el editor"],
        "actions": {
          "save": { "label": "Guardar", "keys": { "es": "ctrl+g", "en": "ctrl+s" } },
          "export": { "label": "Exportar", "keys": "ctrl+shift+e" }
        }
      }
    ]
  }
  ```

  Las teclas pasan por el mismo filtro que las de Nyx (nada de combinaciones peligrosas) y
  nunca se usan en juegos ni en Nyx. Con idiomas, hace falta `*` o `en`.
- **`knowledge/*.md`**: hasta 40 archivos de 64 KB. Nyx los consulta cuando se le pregunta por
  el tema y los trata como información de fuera (nunca como órdenes). Usa títulos `##` claros:
  Nyx busca por ellos.
- **`presets/*.json`**: `name`, `description` y `settings` con solo apariencia, voz y tono
  (nunca seguridad, privacidad, red ni el cerebro).
- **`personality.json`**: `name`, `tone` (`cercano`, `neutro`, `divertido`) y `phrases`: tus
  variantes (de 1 a 12, texto llano) para las respuestas fijas de Nyx.
- **`shape/`**: una forma de Nyx con un shader GLSL. El contrato está en
  [formas.md](formas.md).

## 9. Probar

Con pytest y el Nyx falso del SDK (`sdk/`, MIT, sin dependencias), sin Nyx ni red:

```python
from pathlib import Path

from nyx_sdk.testing import ExtensionError, FakeNyx

FOLDER = Path(__file__).resolve().parents[1]


def test_saluda() -> None:
    nyx = FakeNyx(FOLDER, settings={"password": "1234"})
    nyx.answer("notify", None)
    nyx.answer("ws.recv", lambda p: '{"op": 2}')  # una función recibe los datos pedidos
    assert nyx.run("saluda", nombre="Ana") == "Le he mandado un saludo a Ana."
    assert nyx.asked("notify") == [{"title": "Hola", "text": "Saludos a Ana"}]
```

- Como Nyx, dice que no a lo que no esté en tus permisos (`permissions=[]` para probarlo),
  comprueba los argumentos con `tools.json` y pasa todo por JSON.
- `nyx.answer(método, valor o función)`: lo que contesta Nyx. Si la función lanza una
  excepción, tu código recibe un `RuntimeError`, como de verdad.
- `await nyx.call(...)` en pruebas asíncronas; `nyx.module` es tu `main.py` cargado.
- `nyx.Error` dentro de la prueba es `ExtensionError`.

Para el editor y mypy, el SDK trae los tipos de `import nyx` (`nyx-stubs`). Las extensiones
oficiales (`extensions/tepnyx.obs` y `extensions/tepnyx.spotify`) tienen pruebas completas
con un OBS y un Spotify falsos: úsalas de modelo.

Después, `nyx_ext.py run` la prueba encerrada como en Nyx (lo que tocaría tu equipo, como el
volumen, las teclas o el modelo, solo se enseña: «[Nyx haría] …»), y en Nyx con el modo
desarrollador: Ajustes → Extensiones → **Cargar una carpeta** la instala directamente desde
la carpeta en la que trabajas, y **Recargar** la vuelve a leer cuando cambias algo.

## 10. Buenas prácticas

- **Descripciones cortas y concretas.** El modelo de Nyx es pequeño (7B) y elige por ellas:
  «Cambia a otra escena de OBS por su nombre», no un párrafo. Una herramienta, una cosa.
- **Pocos parámetros, con `enum`** cuando haya opciones fijas (`["empezar", "parar"]`).
- **Grupos y palabras clave.** Nyx no le enseña al modelo todas las herramientas a la vez:
  elige grupos por las palabras de la frase. Pon en `keywords` lo que diría la gente, sin
  tildes y como raíces (`grab` encaja con grabar, grabación, grabando). Una palabra muy común
  (`pon`, `abre`) mete tu grupo en frases que no son suyas. Cómo se midió:
  `core/nyx/tools/groups.py` y `docs/benchmarks/grupos-6.20b.md`.
- **Nombres como los dice la gente.** «La escena de charla» tiene que encontrar «Charla»; si
  hay dos parecidas, pregunta cuál en vez de adivinar (mira `pick` en la extensión de OBS).
- **Mensajes para personas.** Qué ha pasado y qué hacer: «OBS no está abierto o no tiene el
  servidor WebSocket activado (en OBS: Herramientas → …)».
- **Rápido.** Una herramienta debería contestar en menos de 2 segundos; lo largo, en segundo
  plano y con `notify` al terminar.
- **Nada que dependa del momento en `green`** si se ve en público o no se puede deshacer.
- **Conocimiento**: incluye en `knowledge/` cómo preparar el programa (como hace OBS) para que
  Nyx pueda guiar al usuario.

## 11. Firmar y publicar

**Toda extensión que se publique pasa por la revisión de Tepnyx**, pida los permisos que pida
(no solo las de permisos delicados). Tepnyx revisa el código, los permisos y que haga lo que
dice, y la firma (Ed25519 sobre la huella de cada archivo): solo las firmadas se instalan sin
el modo desarrollador y salen en la tienda. Sin firma, solo con el modo desarrollador y como
«Sin revisar», para probar las tuyas. Si Tepnyx retira una extensión (lista de revocación
firmada), Nyx la desactiva y dice por qué.

**Recompensa por publicar:** quien publique una extensión (revisada y aprobada) recibe **10 €
de saldo en su cuenta de Tepnyx**. Está por decidir si se puede gastar en todo Tepnyx o solo en
extensiones.

La tienda llegará con Nyx 1.0 en tepnyx.com. Hasta entonces, si quieres que Tepnyx revise y
firme la tuya, escribe a Tepnyx. Las extensiones de pago serán siempre de pago único.

Si pide permisos delicados, envía antes la solicitud:

```powershell
uv run python scripts/nyx_ext.py pack mi-extension
# sube el .nyxext a una dirección https (una Release de GitHub, tu web…)
uv run python scripts/nyx_ext.py solicitar mi-extension-1.0.0.nyxext `
  --url https://ejemplo.com/mi-extension-1.0.0.nyxext --contacto tu@correo.com
uv run python scripts/nyx_ext.py estado <número>
```

Tepnyx recibe qué es, cada permiso con su porqué, tus herramientas y la huella (SHA-256) de ese
paquete exacto. Lo baja, comprueba la huella, revisa el código y aprueba todos los permisos o
solo algunos. Con `estado` ves la respuesta. Lo aprobado va dentro de la firma: si cambias el
paquete, hace falta otra solicitud.

## 12. Límites

| Qué | Límite |
| --- | --- |
| Paquete | 256 MB, 2.000 archivos, 128 MB por archivo, 12 carpetas de profundidad |
| `manifest.json` | 64 KB |
| Herramientas | 20 por extensión; `tools.json` de 64 KB; 12 parámetros por herramienta |
| Ajustes | 8 por extensión |
| Conocimiento | 40 archivos de 64 KB |
| Llamada a una herramienta | 20 s |
| Red | 1 MB por respuesta, 30 s, 4 WebSocket abiertos |
| Cerebro (`llm.ask`) | 20 preguntas por hora, 4.000 caracteres de pregunta y de respuesta, 90 s |
| Proceso | 512 MB de memoria; 10 % del procesador (3 % en partida) |

## 13. Ejemplos

- **Una herramienta**: la plantilla de `nyx_ext.py new --tipo tools`, y las dos oficiales:
  [`extensions/tepnyx.obs`](../../extensions/tepnyx.obs) (WebSocket local, contraseña en
  Ajustes, nombres como los dice la gente) y
  [`extensions/tepnyx.spotify`](../../extensions/tepnyx.spotify) (API web, inicio de sesión en
  segundo plano, abrir su app).
- **Una forma**: `nyx_ext.py new --tipo shape` y [formas.md](formas.md).
- **Un modo**: llegará con el sistema de modos (tarea 7.10).
