r"""Lo que una extensión con código puede pedir a Nyx, con su permiso comprobado (7.07).

La extensión corre encerrada (sandbox.py): sin red, sin tus archivos, sin ver la pantalla. Lo
que necesita se lo pide a Nyx por `nyx.ask(método, datos)` (runner.py), y Nyx solo lo hace si
el manifiesto lo pide y el usuario lo ha aceptado (HOJA-DE-RUTA §4.5):

| Método                           | Permiso                    |
| -------------------------------- | -------------------------- |
| net.fetch                        | net:<servidor>:<puerto>    |
| ws.open · ws.send · ws.recv · ws.close | net:<servidor>:<puerto> (OBS: localhost:4455) |
| secrets.get · secrets.set · secrets.delete | secrets (Administrador de credenciales) |
| notify                           | notify                     |
| clipboard.read · clipboard.write | clipboard:read / :write    |
| files.list · files.read          | files:read:<carpeta>       |
| files.write                      | files:write:<carpeta> (lo que se sustituye, a la papelera) |

Lo que no está aquí no existe para una extensión: nada de teclas en juegos, ni de leer su
memoria, ni de inyectarse.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from nyx.bus import EventBus
from nyx.events import BubbleShown
from nyx.ext.manifest import KNOWN_FOLDERS, parse_permission
from nyx.ext.rpc import Handler, RpcError

log = logging.getLogger(__name__)

MAX_BODY = 1024 * 1024  # 1 MB por respuesta de red o archivo leído
MAX_SOCKETS = 4
MAX_RECV_S = 30.0

#: Carpetas que una extensión puede pedir, como en el manifiesto.
FolderMap = Callable[[], dict[str, Path]]


class ExtensionApi:
    def __init__(
        self,
        bus: EventBus,
        permissions: Callable[[str], tuple[str, ...]],
        *,
        folders: FolderMap | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """`permissions(id)`: los permisos aceptados de esa extensión (vacío si no está)."""
        self.bus = bus
        self._permissions = permissions
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
            "notify": bind(self.notify),
            "clipboard.read": bind(self.clipboard_read),
            "clipboard.write": bind(self.clipboard_write),
            "files.list": bind(self.files_list),
            "files.read": bind(self.files_read),
            "files.write": bind(self.files_write),
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
