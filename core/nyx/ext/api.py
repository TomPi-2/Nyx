r"""Lo que una extensión con código puede pedir a Nyx, con su permiso comprobado (7.07).

La extensión corre encerrada (sandbox.py): sin red, sin tus archivos, sin ver la pantalla. Lo
que necesita se lo pide a Nyx por `nyx.ask(método, datos)` (runner.py), y Nyx solo lo hace si
el manifiesto lo pide y el usuario lo ha aceptado (HOJA-DE-RUTA §4.5):

| Método                           | Permiso                    |
| -------------------------------- | -------------------------- |
| net.fetch                        | net:<servidor>:<puerto>    |
| ws.open · ws.send · ws.recv · ws.close | net:<servidor>:<puerto> (OBS: localhost:4455) |
| secrets.get · secrets.set · secrets.delete | secrets (Administrador de credenciales) |
| settings.get                     | ninguno: los ajustes de su manifiesto, que pone el usuario |
| oauth.authorize                  | net:<servidor>:443 de las dos direcciones (iniciar sesión) |
| open.uri                         | apps:launch (su app por su esquema, o sus webs)            |
| notify                           | notify                     |
| clipboard.read · clipboard.write | clipboard:read / :write    |
| files.list · files.read          | files:read:<carpeta>       |
| files.write                      | files:write:<carpeta> (lo que se sustituye, a la papelera) |
| apps.open                        | apps:launch (una app por su nombre, como «abre Spotify») |
| audio.volume                     | audio                      |
| media.control · media.playing    | media                      |
| ui.panel                         | ui:panel (el panel largo de Nyx: texto o secciones) |
| llm.ask                          | llm (el modelo de Nyx; nunca en partida, con cupo por hora) |
| apps.window · apps.action · apps.keys | apps:control:<app> (solo esa app; nunca en partida) |

Los delicados (files:write, clipboard:read, apps:control, llm, messages) necesitan además la
aprobación de Tepnyx dentro de la firma (store.py). `messages:<servicio>` no tiene método: la
extensión envía con su propia red, y el permiso sube sus herramientas a rojo (Nyx pregunta
antes de cada envío).

Lo que no está aquí no existe para una extensión: nada de teclas en juegos, ni de leer su
memoria, ni de inyectarse.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import logging
import os
import secrets as pysecrets
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

from nyx.bus import EventBus
from nyx.events import BubbleShown, LongSection
from nyx.ext.manifest import KNOWN_FOLDERS, parse_permission
from nyx.ext.rpc import Handler, RpcError

log = logging.getLogger(__name__)

MAX_BODY = 1024 * 1024  # 1 MB por respuesta de red o archivo leído
#: Esquemas de apps que una extensión con `apps:launch` puede abrir. Lista cerrada: nada de
#: `file:`, `ms-settings:` ni otros que lancen programas cualesquiera.
APP_SCHEMES = frozenset({"spotify"})
MAX_SOCKETS = 4
MAX_RECV_S = 30.0
#: `llm.ask`: preguntas por hora y extensión, y tamaño de lo que se pregunta y se devuelve.
LLM_PER_HOUR = 20
MAX_PROMPT = 4000
#: `ui.panel`: lo que cabe en el panel largo.
MAX_SECTIONS = 6
MAX_ITEMS = 20
#: `apps.window`: lo que una extensión con `apps:control:<app>` puede hacer con su ventana.
WINDOW_ACTIONS = frozenset({"focus", "minimize", "maximize", "restore", "close"})

#: Carpetas que una extensión puede pedir, como en el manifiesto.
FolderMap = Callable[[], dict[str, Path]]
#: Ejecuta una herramienta de Nyx ya comprobada (nombre, argumentos) → (bien, lo que dice).
ToolRunner = Callable[[str, dict[str, Any]], Awaitable[tuple[bool, str]]]
#: Pregunta al modelo de Nyx (instrucciones, pregunta) → respuesta.
LlmAsker = Callable[[str, str], Awaitable[str]]


class ExtensionApi:
    def __init__(
        self,
        bus: EventBus,
        permissions: Callable[[str], tuple[str, ...]],
        *,
        folders: FolderMap | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        settings_of: Callable[[str], tuple[str, ...]] | None = None,
        setting_reader: Callable[[str, str], str | None] | None = None,
        open_url: Callable[[str], None] | None = None,
        playing: Callable[[], bool] = lambda: False,
        run_tool: ToolRunner | None = None,
        ask_llm: LlmAsker | None = None,
        clock: Callable[[], float] = time.monotonic,
        offline: Callable[[], bool] = lambda: False,
    ) -> None:
        """`permissions(id)`: los permisos aceptados de esa extensión (vacío si no está).
        `settings_of(id)`: las claves de `settings` de su manifiesto. `open_url`: abre una
        URI ya comprobada (en Windows, `os.startfile`). `playing()`: si hay partida.
        `run_tool`: las herramientas de Nyx que reutilizan apps, sonido y ventanas (sin ella,
        esos métodos dicen que no están). `ask_llm`: el modelo de Nyx (`llm.ask`)."""
        self.bus = bus
        self._permissions = permissions
        self._settings_of = settings_of or (lambda _id: ())
        self._read_setting = setting_reader or read_setting
        self._open_url = open_url or _open_url
        self._playing = playing
        self._run_tool = run_tool
        self._ask_llm = ask_llm
        self._clock = clock
        self._offline = offline
        self._llm_calls: dict[str, list[float]] = {}
        self._logins: set[str] = set()
        self._folders = folders or _known_folders
        self._transport = transport
        self._sockets: dict[str, dict[int, Any]] = {}
        self._next = 0

    def handlers(self, ext_id: str) -> dict[str, Handler]:
        def bind(fn: Callable[[str, dict[str, Any]], Any]) -> Handler:
            async def handle(params: dict[str, Any]) -> Any:
                return await fn(ext_id, params)

            return handle

        return {
            "net.fetch": bind(self.fetch),
            "ws.open": bind(self.ws_open),
            "ws.send": bind(self.ws_send),
            "ws.recv": bind(self.ws_recv),
            "ws.close": bind(self.ws_close),
            "secrets.get": bind(self.secret_get),
            "secrets.set": bind(self.secret_set),
            "secrets.delete": bind(self.secret_delete),
            "settings.get": bind(self.setting_get),
            "oauth.authorize": bind(self.oauth_authorize),
            "open.uri": bind(self.open_uri),
            "notify": bind(self.notify),
            "clipboard.read": bind(self.clipboard_read),
            "clipboard.write": bind(self.clipboard_write),
            "files.list": bind(self.files_list),
            "files.read": bind(self.files_read),
            "files.write": bind(self.files_write),
            "apps.open": bind(self.apps_open),
            "audio.volume": bind(self.audio_volume),
            "media.control": bind(self.media_control),
            "media.playing": bind(self.media_playing),
            "ui.panel": bind(self.ui_panel),
            "llm.ask": bind(self.llm_ask),
            "apps.window": bind(self.apps_window),
            "apps.action": bind(self.apps_action),
            "apps.keys": bind(self.apps_keys),
        }

    async def close(self, ext_id: str) -> None:
        """La extensión se ha parado: se cierran sus conexiones."""
        for ws in self._sockets.pop(ext_id, {}).values():
            with contextlib.suppress(Exception):
                await ws.close()

    # --- Permisos -------------------------------------------------------------------------------

    def _need(self, ext_id: str, kind: str, target: str = "") -> None:
        for text in self._permissions(ext_id):
            p = parse_permission(text)
            if p.kind == kind and (not target or p.target == target):
                return
        wanted = f"{kind}:{target}" if target else kind
        log.warning("Extensión %s: pide algo sin permiso (%s)", ext_id, wanted)
        raise RpcError(f"sin permiso «{wanted}»")

    def _need_host(self, ext_id: str, url: str, schemes: tuple[str, ...]) -> str:
        if self._offline():
            raise RpcError("sin internet: Nyx está en modo Privacidad")
        parts = urlsplit(url)
        if parts.scheme not in schemes or not parts.hostname:
            raise RpcError(f"dirección no válida: {url[:200]}")
        secure = parts.scheme in ("https", "wss")
        port = parts.port or (443 if secure else 80)
        self._need(ext_id, "net", f"{parts.hostname.lower()}:{port}")
        return url

    # --- Red ------------------------------------------------------------------------------------

    async def fetch(self, ext_id: str, p: dict[str, Any]) -> dict[str, Any]:
        url = self._need_host(ext_id, str(p.get("url", "")), ("http", "https"))
        method = str(p.get("method", "GET")).upper()
        if method not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
            raise RpcError(f"método no admitido: {method}")
        headers = {str(k): str(v) for k, v in dict(p.get("headers") or {}).items()}
        body = p.get("body")
        timeout = min(float(p.get("timeout_s", 15)), 30.0)
        # Sin seguir redirecciones: podrían llevar a otro servidor sin permiso.
        async with httpx.AsyncClient(
            timeout=timeout, follow_redirects=False, transport=self._transport
        ) as http:
            try:
                resp = await http.request(
                    method, url, headers=headers, content=None if body is None else str(body)
                )
            except httpx.HTTPError as e:
                raise RpcError(f"no se ha podido conectar: {e}") from e
        return {
            "status": resp.status_code,
            "headers": {k: v for k, v in resp.headers.items() if k.lower() == "content-type"},
            "body": resp.text[:MAX_BODY],
        }

    async def ws_open(self, ext_id: str, p: dict[str, Any]) -> int:
        url = self._need_host(ext_id, str(p.get("url", "")), ("ws", "wss"))
        mine = self._sockets.setdefault(ext_id, {})
        if len(mine) >= MAX_SOCKETS:
            raise RpcError("demasiadas conexiones abiertas")
        import websockets

        try:
            ws = await asyncio.wait_for(
                websockets.connect(url, max_size=MAX_BODY, open_timeout=10), 12
            )
        except (OSError, TimeoutError, websockets.WebSocketException) as e:
            raise RpcError(f"no se ha podido conectar: {e}") from e
        self._next += 1
        mine[self._next] = ws
        return self._next

    def _socket(self, ext_id: str, p: dict[str, Any]) -> Any:
        ws = self._sockets.get(ext_id, {}).get(int(p.get("id", -1)))
        if ws is None:
            raise RpcError("conexión desconocida o cerrada")
        return ws

    async def ws_send(self, ext_id: str, p: dict[str, Any]) -> None:
        text = str(p.get("text", ""))
        if len(text) > MAX_BODY:
            raise RpcError("mensaje demasiado grande")
        try:
            await self._socket(ext_id, p).send(text)
        except Exception as e:
            raise RpcError(f"no se ha podido enviar: {e}") from e

    async def ws_recv(self, ext_id: str, p: dict[str, Any]) -> str | None:
        ws = self._socket(ext_id, p)
        timeout = min(float(p.get("timeout_s", 10)), MAX_RECV_S)
        try:
            message = await asyncio.wait_for(ws.recv(), timeout)
        except TimeoutError:
            return None
        except Exception as e:
            raise RpcError(f"la conexión se ha cerrado: {e}") from e
        return message if isinstance(message, str) else message.decode("utf-8", "replace")

    async def ws_close(self, ext_id: str, p: dict[str, Any]) -> None:
        ws = self._sockets.get(ext_id, {}).pop(int(p.get("id", -1)), None)
        if ws is not None:
            with contextlib.suppress(Exception):
                await ws.close()

    # --- Secretos (Administrador de credenciales de Windows) ---------------------------------

    @staticmethod
    def _target(ext_id: str, p: dict[str, Any]) -> str:
        key = str(p.get("key", ""))
        if not key or len(key) > 64 or not all(c.isalnum() or c in "-_." for c in key):
            raise RpcError("nombre de clave no válido")
        return f"Nyx/ext/{ext_id}/{key}"

    async def secret_get(self, ext_id: str, p: dict[str, Any]) -> str | None:
        self._need(ext_id, "secrets")
        return await asyncio.to_thread(_cred_read, self._target(ext_id, p))

    async def secret_set(self, ext_id: str, p: dict[str, Any]) -> None:
        self._need(ext_id, "secrets")
        value = str(p.get("value", ""))
        if len(value) > 2048:
            raise RpcError("el secreto es demasiado largo")
        await asyncio.to_thread(_cred_write, self._target(ext_id, p), value)

    async def secret_delete(self, ext_id: str, p: dict[str, Any]) -> None:
        self._need(ext_id, "secrets")
        await asyncio.to_thread(_cred_delete, self._target(ext_id, p))

    # --- Ajustes que pone el usuario (7.14) ---------------------------------------------------

    async def setting_get(self, ext_id: str, p: dict[str, Any]) -> str | None:
        key = str(p.get("key", ""))
        if key not in self._settings_of(ext_id):
            raise RpcError(f"«{key[:40]}» no está en los ajustes de su manifiesto")
        return await asyncio.to_thread(self._read_setting, ext_id, key)

    # --- Iniciar sesión en un servicio (OAuth 2 con PKCE; 7.14) --------------------------------

    async def oauth_authorize(self, ext_id: str, p: dict[str, Any]) -> dict[str, Any]:
        """Abre el navegador para que el usuario entre en el servicio y devuelve sus tokens.

        Nyx escucha la vuelta en 127.0.0.1 (puerto libre) y cambia el código por los tokens con
        PKCE: la extensión no ve la contraseña ni el navegador. Las dos direcciones tienen que
        estar en sus permisos de red. Nunca en partida.
        """
        authorize = self._need_host(ext_id, str(p.get("authorize_url", "")), ("https",))
        token_url = self._need_host(ext_id, str(p.get("token_url", "")), ("https",))
        client_id = str(p.get("client_id", "")).strip()
        scopes = str(p.get("scopes", "")).strip()
        if not client_id or len(client_id) > 200 or len(scopes) > 1000:
            raise RpcError("falta el identificador de la app (client_id)")
        if self._playing():
            raise RpcError("en partida no se inicia sesión: al terminar")
        if ext_id in self._logins:
            raise RpcError("ya hay un inicio de sesión abierto")
        self._logins.add(ext_id)
        try:
            return await _oauth_flow(
                authorize,
                token_url,
                client_id,
                scopes,
                open_url=self._open_url,
                transport=self._transport,
                timeout_s=min(float(p.get("timeout_s", 180)), 300.0),
            )
        finally:
            self._logins.discard(ext_id)

    # --- Abrir su app o sus webs (7.14) ---------------------------------------------------------

    async def open_uri(self, ext_id: str, p: dict[str, Any]) -> None:
        self._need(ext_id, "apps:launch")
        uri = str(p.get("uri", ""))
        if len(uri) > 2000 or not uri.isprintable():
            raise RpcError("dirección no válida")
        scheme = uri.split(":", 1)[0].lower()
        if scheme == "https":
            self._need_host(ext_id, uri, ("https",))
        elif scheme not in APP_SCHEMES:
            raise RpcError(f"solo se pueden abrir {', '.join(sorted(APP_SCHEMES))}: y sus webs")
        await asyncio.to_thread(self._open_url, uri)

    # --- Avisos y portapapeles ----------------------------------------------------------------

    async def notify(self, ext_id: str, p: dict[str, Any]) -> None:
        self._need(ext_id, "notify")
        title = str(p.get("title", "")).strip()[:80] or "Aviso"
        text = str(p.get("text", "")).strip()[:200]
        await self.bus.publish(BubbleShown(display=title, secondary=text or None, alert=True))

    async def clipboard_read(self, ext_id: str, p: dict[str, Any]) -> str:
        self._need(ext_id, "clipboard:read")
        return (await asyncio.to_thread(_clip_get))[:MAX_BODY]

    async def clipboard_write(self, ext_id: str, p: dict[str, Any]) -> None:
        self._need(ext_id, "clipboard:write")
        text = str(p.get("text", ""))
        if len(text) > MAX_BODY:
            raise RpcError("texto demasiado largo")
        await asyncio.to_thread(_clip_set, text)

    # --- Apps, sonido y ventanas (con las herramientas de Nyx) ----------------------------------

    async def _tool(self, name: str, args: dict[str, Any]) -> str:
        """Ejecuta una herramienta de Nyx; si no sale, la extensión recibe el porqué."""
        if self._run_tool is None:
            raise RpcError("esta versión de Nyx no lo permite")
        ok, message = await self._run_tool(name, args)
        if not ok:
            raise RpcError(message[:300] or "no ha salido")
        return message[:300]

    def _not_in_game(self, what: str) -> None:
        if self._playing():
            raise RpcError(f"en partida no se puede {what}")

    @staticmethod
    def _text(p: dict[str, Any], key: str, limit: int, *, required: bool = True) -> str:
        value = p.get(key)
        if value is None and not required:
            return ""
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise RpcError(f"«{key}» tiene que ser un texto de 1 a {limit} caracteres")
        return value.strip()

    async def apps_open(self, ext_id: str, p: dict[str, Any]) -> str:
        self._need(ext_id, "apps:launch")
        self._not_in_game("abrir apps")
        return await self._tool("open_app", {"name": self._text(p, "name", 100)})

    async def audio_volume(self, ext_id: str, p: dict[str, Any]) -> str:
        self._need(ext_id, "audio")
        args: dict[str, Any] = {}
        for key in ("level", "change"):
            if key in p:
                value = p[key]
                if not isinstance(value, int) or isinstance(value, bool):
                    raise RpcError(f"«{key}» tiene que ser un número entero")
                args[key] = value
        if "mute" in p:
            if not isinstance(p["mute"], bool):
                raise RpcError("«mute» tiene que ser true o false")
            args["mute"] = p["mute"]
        if not args:
            raise RpcError("di «level», «change» o «mute»")
        return await self._tool("set_volume", args)

    async def media_control(self, ext_id: str, p: dict[str, Any]) -> str:
        self._need(ext_id, "media")
        args: dict[str, Any] = {"action": self._text(p, "action", 20)}
        if source := self._text(p, "source", 60, required=False):
            args["source"] = source
        return await self._tool("media_control", args)

    async def media_playing(self, ext_id: str, p: dict[str, Any]) -> str:
        self._need(ext_id, "media")
        return await self._tool("now_playing", {})

    async def ui_panel(self, ext_id: str, p: dict[str, Any]) -> None:
        self._need(ext_id, "ui:panel")
        title = self._text(p, "title", 80)
        text = self._text(p, "text", MAX_BODY // 256, required=False)  # 4 KB
        raw = p.get("sections", [])
        if not isinstance(raw, list) or len(raw) > MAX_SECTIONS:
            raise RpcError(f"«sections» tiene que ser una lista de hasta {MAX_SECTIONS}")
        sections: list[LongSection] = []
        for s in raw:
            if not isinstance(s, dict):
                raise RpcError("cada sección es {title, items, ordered}")
            items = s.get("items", [])
            if (
                not isinstance(items, list)
                or not 0 < len(items) <= MAX_ITEMS
                or not all(isinstance(i, str) and 0 < len(i) <= 200 for i in items)
            ):
                raise RpcError(f"«items»: de 1 a {MAX_ITEMS} textos de hasta 200 caracteres")
            sections.append(
                LongSection(
                    title=self._text(s, "title", 60),
                    items=tuple(i.strip() for i in items),
                    ordered=bool(s.get("ordered", False)),
                )
            )
        if not text and not sections:
            raise RpcError("el panel necesita «text» o «sections»")
        await self.bus.publish(
            BubbleShown(display=title, kind="long", text=text, sections=tuple(sections))
        )

    async def llm_ask(self, ext_id: str, p: dict[str, Any]) -> str:
        self._need(ext_id, "llm")
        # En partida, la gráfica es del juego (SPEC §9): el modelo solo piensa para Nyx.
        self._not_in_game("usar el modelo")
        if self._ask_llm is None:
            raise RpcError("esta versión de Nyx no lo permite")
        prompt = self._text(p, "prompt", MAX_PROMPT)
        system = self._text(p, "system", 1000, required=False)
        now = self._clock()
        recent = [t for t in self._llm_calls.get(ext_id, []) if now - t < 3600]
        if len(recent) >= LLM_PER_HOUR:
            raise RpcError(f"ya ha preguntado {LLM_PER_HOUR} veces esta hora")
        self._llm_calls[ext_id] = [*recent, now]
        try:
            answer = await asyncio.wait_for(self._ask_llm(system, prompt), 90)
        except TimeoutError as e:
            raise RpcError("el modelo ha tardado demasiado") from e
        return answer[:MAX_PROMPT]

    def _controlled(self, ext_id: str, p: dict[str, Any]) -> str:
        """La app que controla: tiene que ser la de su permiso `apps:control:<app>`."""
        app = self._text(p, "app", 48).lower()
        self._need(ext_id, "apps:control", app)
        self._not_in_game("controlar apps")
        return app

    async def apps_window(self, ext_id: str, p: dict[str, Any]) -> str:
        app = self._controlled(ext_id, p)
        action = self._text(p, "action", 20)
        if action not in WINDOW_ACTIONS:
            raise RpcError(f"«action»: {', '.join(sorted(WINDOW_ACTIONS))}")
        if action == "focus":
            return await self._tool("focus_window", {"name": app})
        if action == "close":
            return await self._tool("close_app", {"name": app})
        return await self._tool("window_layout", {"action": action, "name": app})

    async def apps_action(self, ext_id: str, p: dict[str, Any]) -> str:
        app = self._controlled(ext_id, p)
        times = p.get("times", 1)
        if not isinstance(times, int) or isinstance(times, bool) or not 1 <= times <= 10:
            raise RpcError("«times» va de 1 a 10")
        action = self._text(p, "action", 40)
        return await self._tool("app_action", {"action": action, "app": app, "times": times})

    async def apps_keys(self, ext_id: str, p: dict[str, Any]) -> str:
        app = self._controlled(ext_id, p)
        return await self._tool("send_hotkey", {"keys": self._text(p, "keys", 40), "app": app})

    # --- Archivos (solo en las carpetas con permiso) ------------------------------------------

    def _path(self, ext_id: str, p: dict[str, Any], mode: str) -> Path:
        folder = str(p.get("folder", ""))
        if folder not in KNOWN_FOLDERS:
            raise RpcError(f"carpeta desconocida: {folder[:40]}")
        self._need(ext_id, f"files:{mode}", folder)
        base = self._folders().get(folder)
        if base is None:
            raise RpcError("no encuentro esa carpeta en este equipo")
        rel = str(p.get("path", ""))
        target = (base / rel).resolve()
        if not target.is_relative_to(base.resolve()):
            raise RpcError("ruta fuera de la carpeta permitida")
        return target

    async def files_list(self, ext_id: str, p: dict[str, Any]) -> list[dict[str, Any]]:
        target = self._path(ext_id, p, "read")

        def run() -> list[dict[str, Any]]:
            if not target.is_dir():
                raise RpcError("no es una carpeta")
            return [
                {"name": e.name, "dir": e.is_dir(), "size": e.stat().st_size if e.is_file() else 0}
                for e in sorted(target.iterdir())[:500]
            ]

        return await asyncio.to_thread(run)

    async def files_read(self, ext_id: str, p: dict[str, Any]) -> dict[str, Any]:
        target = self._path(ext_id, p, "read")

        def run() -> dict[str, Any]:
            if not target.is_file():
                raise RpcError("no existe ese archivo")
            if target.stat().st_size > MAX_BODY:
                raise RpcError("el archivo es demasiado grande (más de 1 MB)")
            data = target.read_bytes()
            try:
                return {"text": data.decode("utf-8")}
            except UnicodeDecodeError:
                return {"base64": base64.b64encode(data).decode("ascii")}

        return await asyncio.to_thread(run)

    async def files_write(self, ext_id: str, p: dict[str, Any]) -> None:
        target = self._path(ext_id, p, "write")
        text = p.get("text")
        raw = p.get("base64")
        data = str(text).encode("utf-8") if text is not None else base64.b64decode(str(raw or ""))
        if len(data) > MAX_BODY:
            raise RpcError("demasiado grande (más de 1 MB)")

        def run() -> None:
            from send2trash import send2trash

            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                send2trash(str(target))  # lo que había, a la papelera (nunca borrado del todo)
            target.write_bytes(data)

        await asyncio.to_thread(run)


# --- OAuth ------------------------------------------------------------------------------------

_DONE_PAGE = (
    "<!doctype html><meta charset=utf-8><title>Nyx</title>"
    "<body style='font-family:Segoe UI,sans-serif;background:#1c1c1e;color:#eee;"
    "display:grid;place-items:center;height:100vh;margin:0'>"
    "<p style='font-size:18px'>{text}</p>"
)


async def _oauth_flow(
    authorize_url: str,
    token_url: str,
    client_id: str,
    scopes: str,
    *,
    open_url: Callable[[str], None],
    transport: httpx.AsyncBaseTransport | None,
    timeout_s: float,
) -> dict[str, Any]:
    verifier = pysecrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    state = pysecrets.token_urlsafe(16)
    got: asyncio.Future[dict[str, str]] = asyncio.get_running_loop().create_future()

    async def on_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            line = (await asyncio.wait_for(reader.readline(), 10)).decode("latin-1")
            target = line.split(" ")[1] if line.count(" ") >= 2 else ""
            parts = urlsplit(target)
            query = {k: v[0] for k, v in parse_qs(parts.query).items()}
            ok = parts.path == "/callback" and query.get("state") == state
            text = (
                "Listo: ya puedes cerrar esta pestaña y volver con Nyx."
                if ok and "code" in query
                else "No se ha podido iniciar sesión. Vuelve a pedírselo a Nyx."
            )
            body = _DONE_PAGE.format(text=text).encode()
            head = (
                "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
                f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n"
            )
            writer.write(head.encode() + body)
            await writer.drain()
            if ok and not got.done():
                got.set_result(query)
        except OSError, TimeoutError, ValueError, IndexError:
            pass
        finally:
            writer.close()

    server = await asyncio.start_server(on_client, "127.0.0.1", 0)
    try:
        port = server.sockets[0].getsockname()[1]
        redirect = f"http://127.0.0.1:{port}/callback"
        query = {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
            "state": state,
        }
        if scopes:
            query["scope"] = scopes
        await asyncio.to_thread(open_url, f"{authorize_url}?{urlencode(query)}")
        try:
            answer = await asyncio.wait_for(got, timeout_s)
        except TimeoutError:
            raise RpcError("no se ha terminado de iniciar sesión a tiempo") from None
    finally:
        server.close()
    if "code" not in answer:
        raise RpcError(f"el servicio no ha dado permiso ({answer.get('error', 'cancelado')})")
    form = {
        "grant_type": "authorization_code",
        "code": answer["code"],
        "redirect_uri": redirect,
        "client_id": client_id,
        "code_verifier": verifier,
    }
    async with httpx.AsyncClient(timeout=15, follow_redirects=False, transport=transport) as http:
        try:
            resp = await http.post(token_url, data=form)
        except httpx.HTTPError as e:
            raise RpcError(f"no se ha podido conectar: {e}") from e
    try:
        tokens = resp.json()
    except ValueError:
        tokens = None
    if resp.status_code != 200 or not isinstance(tokens, dict) or "access_token" not in tokens:
        raise RpcError(f"el servicio no ha dado los tokens ({resp.status_code})")
    keep = ("access_token", "refresh_token", "expires_in", "scope", "token_type")
    return {k: tokens[k] for k in keep if k in tokens}


def _open_url(uri: str) -> None:
    os.startfile(uri)  # solo Windows; la URI ya está comprobada


# --- Ajustes de las extensiones (los escribe Ajustes, nunca la extensión) ---------------------


def setting_target(ext_id: str, key: str) -> str:
    """Aparte de sus secretos (`Nyx/ext/…`): con `secrets.set` no puede cambiar un ajuste."""
    return f"Nyx/ext-ajustes/{ext_id}/{key}"


def read_setting(ext_id: str, key: str) -> str | None:
    return _cred_read(setting_target(ext_id, key))


def write_setting(ext_id: str, key: str, value: str) -> None:
    """Guarda un ajuste; vacío, lo quita."""
    if len(value) > 2048:
        raise ValueError("demasiado largo")
    if value:
        _cred_write(setting_target(ext_id, key), value)
    else:
        _cred_delete(setting_target(ext_id, key))


def forget(ext_id: str) -> None:
    """Al desinstalarla: fuera sus secretos y sus ajustes del Administrador de credenciales."""
    import pywintypes
    import win32cred

    for pattern in (f"Nyx/ext/{ext_id}/*", f"Nyx/ext-ajustes/{ext_id}/*"):
        try:
            found = win32cred.CredEnumerate(pattern, 0) or ()
        except pywintypes.error:
            continue  # no hay ninguno
        for cred in found:
            _cred_delete(str(cred["TargetName"]))


def _known_folders() -> dict[str, Path]:
    from nyx.index.scanners.folders import known_folders

    found = known_folders()
    names = {
        "documentos": ("documentos", "documents"),
        "descargas": ("descargas", "downloads"),
        "escritorio": ("escritorio", "desktop"),
        "imagenes": ("imagenes", "imágenes", "pictures"),
        "musica": ("musica", "música", "music"),
        "videos": ("videos", "vídeos"),
    }
    out: dict[str, Path] = {}
    for key, aliases in names.items():
        for name, path in found.items():
            if name.lower() in aliases:
                out[key] = Path(path)
                break
    return out


def _cred_read(target: str) -> str | None:
    import pywintypes
    import win32cred

    try:
        cred = win32cred.CredRead(target, win32cred.CRED_TYPE_GENERIC)
    except pywintypes.error:
        return None
    blob = cred.get("CredentialBlob") or b""
    return blob.decode("utf-16-le") if isinstance(blob, bytes) else str(blob)


def _cred_write(target: str, value: str) -> None:
    import win32cred

    win32cred.CredWrite(
        {
            "Type": win32cred.CRED_TYPE_GENERIC,
            "TargetName": target,
            "CredentialBlob": value,
            "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE,
            "UserName": "Nyx",
        },
        0,
    )


def _cred_delete(target: str) -> None:
    import pywintypes
    import win32cred

    with contextlib.suppress(pywintypes.error):
        win32cred.CredDelete(target, win32cred.CRED_TYPE_GENERIC)


def _clip_get() -> str:
    from nyx.tools.clipboard import read_clipboard_text

    return read_clipboard_text() or ""


def _clip_set(text: str) -> None:
    from nyx.tools.clipboard import write_clipboard_text

    write_clipboard_text(text)
