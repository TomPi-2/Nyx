# SPDX-License-Identifier: MIT
"""Un Nyx falso para probar una extensión con código sin Nyx (tarea 7.12).

Carga `tools/main.py` como lo hace Nyx (con `tools/lib` para sus dependencias), le da un módulo
`nyx` falso y deja llamar a sus herramientas. Lo que la extensión pide con `nyx.ask` se apunta
en `asks` y se contesta con lo que le digas en `answer`; como en Nyx, **sin el permiso en el
manifiesto se le dice que no**. Los argumentos y lo que devuelve pasan por JSON, como de verdad.

    from nyx_sdk.testing import FakeNyx

    def test_graba() -> None:
        nyx = FakeNyx("mi-extension")
        nyx.answer("ws.open", 1)
        nyx.answer("ws.recv", lambda p: '{"op": 2, "d": {}}')
        assert nyx.run("obs_start_recording") == "Grabando"
        assert nyx.asked("ws.send")

Diferencias con Nyx: aquí la extensión **no** corre encerrada ni con límites de memoria o de
procesador, y `nyx.data_dir` es una carpeta temporal. Para probarla de verdad, encerrada y con
la red de verdad: `nyx-ext run`.
"""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import json
import sys
import tempfile
import types
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

API = "1.0"

#: Lo que se puede pedir a Nyx y el permiso que hace falta (None: no pide permiso propio).
_FILES = {"files.list": "read", "files.read": "read", "files.write": "write"}
_PLAIN = {
    "secrets.get": "secrets",
    "secrets.set": "secrets",
    "secrets.delete": "secrets",
    "notify": "notify",
    "clipboard.read": "clipboard:read",
    "clipboard.write": "clipboard:write",
}
_SOCKET = ("ws.send", "ws.recv", "ws.close")
#: Apps que se pueden abrir con `open.uri` (como `APP_SCHEMES` en Nyx).
APP_SCHEMES = frozenset({"spotify"})
_JSON_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
}


class PermissionDeniedError(RuntimeError):
    """Lo que dice Nyx cuando la extensión pide algo sin permiso."""


class ExtensionError(Exception):
    """`nyx.Error` dentro de la extensión: lo que el usuario leería tal cual."""


class FakeNyx:
    def __init__(
        self,
        folder: str | Path,
        *,
        permissions: Iterable[str] | None = None,
        data_dir: str | Path | None = None,
        settings: dict[str, str] | None = None,
    ) -> None:
        """`folder`: la carpeta de la extensión (con `manifest.json` y `tools/`).
        `permissions`: los aceptados; por defecto, todos los del manifiesto.
        `settings`: lo que el usuario ha puesto en Ajustes (`settings.get`; sin poner, None)."""
        self.folder = Path(folder)
        self.manifest: dict[str, Any] = json.loads(
            (self.folder / "manifest.json").read_text(encoding="utf-8")
        )
        self.permissions = frozenset(
            self.manifest.get("permissions", []) if permissions is None else permissions
        )
        self.data_dir = Path(data_dir) if data_dir else Path(tempfile.mkdtemp(prefix="nyx-ext-"))
        self.specs: dict[str, dict[str, Any]] = {
            spec["name"]: spec
            for spec in json.loads(
                (self.folder / "tools" / "tools.json").read_text(encoding="utf-8")
            )
        }
        #: Lo que ha pedido la extensión, en orden: (método, datos).
        self.asks: list[tuple[str, dict[str, Any]]] = []
        #: Lo que ha escrito con `print` (y los errores).
        self.logs: list[str] = []
        self.settings = dict(settings or {})
        self._answers: dict[str, Any] = {
            "settings.get": lambda p: self.settings.get(str(p.get("key")))
        }
        self._tools: dict[str, Callable[..., Any]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loaded = False
        #: El `tools/main.py` cargado (para mirar su estado en las pruebas).
        self.module: types.ModuleType | None = None

    # --- Preparar ------------------------------------------------------------------------------

    def answer(self, method: str, value: Any) -> None:
        """Lo que contesta Nyx a `method`: un valor, o una función (normal o asíncrona) que
        recibe los datos de la petición. Si la función lanza una excepción, la extensión recibe
        un RuntimeError, como cuando Nyx dice que no."""
        self._answers[method] = value

    def load(self) -> list[str]:
        """Carga la extensión y devuelve sus herramientas. Falla si `tools.json` describe alguna
        que el código no tiene (en Nyx fallaría al usarla)."""
        if self._loaded:
            return sorted(self._tools)
        tools_dir = self.folder / "tools"
        saved_nyx = sys.modules.get("nyx")
        saved_path = list(sys.path)
        sys.modules["nyx"] = self._module()
        sys.path[:0] = [str(tools_dir), str(tools_dir / "lib")]
        try:
            spec = importlib.util.spec_from_file_location(
                f"_nyx_ext_{id(self)}", tools_dir / "main.py"
            )
            if spec is None or spec.loader is None:
                raise ImportError("no se puede cargar tools/main.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.module = module
        finally:
            # El código de la extensión ya tiene su `nyx`; se deja todo como estaba.
            sys.path[:] = saved_path
            if saved_nyx is None:
                sys.modules.pop("nyx", None)
            else:
                sys.modules["nyx"] = saved_nyx
        missing = sorted(set(self.specs) - set(self._tools))
        if missing:
            raise LookupError(f"tools.json describe herramientas que no existen: {missing}")
        self._loaded = True
        return sorted(self._tools)

    # --- Usar ----------------------------------------------------------------------------------

    async def call(self, tool: str, **args: Any) -> Any:
        """Llama a una herramienta como Nyx: comprueba los argumentos con `tools.json`."""
        self.load()
        if tool not in self.specs:
            raise LookupError(f"«{tool}» no está en tools.json: Nyx no la ofrecería")
        fn = self._tools[tool]
        args = json.loads(json.dumps(args, ensure_ascii=False))
        self._check_args(tool, args)
        self._loop = asyncio.get_running_loop()
        if inspect.iscoroutinefunction(fn):
            result = await fn(**args)
        else:
            result = await asyncio.to_thread(fn, **args)
        return json.loads(json.dumps(result, ensure_ascii=False, default=str))

    def run(self, tool: str, **args: Any) -> Any:
        """`call` desde una prueba normal (no asíncrona)."""
        return asyncio.run(self.call(tool, **args))

    def asked(self, method: str) -> list[dict[str, Any]]:
        """Los datos de cada vez que la extensión pidió `method`."""
        return [params for m, params in self.asks if m == method]

    # --- Por dentro ----------------------------------------------------------------------------

    def _module(self) -> types.ModuleType:
        module = types.ModuleType("nyx", "Nyx falso (nyx_sdk.testing)")

        def tool(fn: Callable[..., Any]) -> Callable[..., Any]:
            self._tools[fn.__name__] = fn
            return fn

        async def ask(
            method: str, params: dict[str, Any] | None = None, timeout_s: float = 30.0
        ) -> Any:
            return await asyncio.wait_for(self._ask(method, params or {}), timeout_s)

        def ask_sync(
            method: str, params: dict[str, Any] | None = None, timeout_s: float = 30.0
        ) -> Any:
            if self._loop is None:
                raise RuntimeError("nyx.ask_sync solo se puede usar dentro de una herramienta")
            future = asyncio.run_coroutine_threadsafe(ask(method, params, timeout_s), self._loop)
            return future.result()

        module.Error = ExtensionError  # type: ignore[attr-defined]
        module.tool = tool  # type: ignore[attr-defined]
        module.ask = ask  # type: ignore[attr-defined]
        module.ask_sync = ask_sync  # type: ignore[attr-defined]
        module.API = API  # type: ignore[attr-defined]
        module.data_dir = self.data_dir  # type: ignore[attr-defined]
        return module

    async def _ask(self, method: str, params: dict[str, Any]) -> Any:
        params = json.loads(json.dumps(params, ensure_ascii=False, default=str))
        self.asks.append((method, params))
        self._check_permission(method, params)
        if method not in self._answers:
            raise RuntimeError(f"FakeNyx: no le has dicho qué contestar a «{method}» (answer)")
        value = self._answers[method]
        if callable(value):
            try:
                value = value(params)
                if inspect.isawaitable(value):
                    value = await value
            except Exception as e:
                raise RuntimeError(str(e)) from e
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))

    def _check_permission(self, method: str, params: dict[str, Any]) -> None:
        if method == "settings.get":
            # Sin permiso: solo los `settings` de su manifiesto (los pone el usuario en Ajustes).
            keys = {s.get("key") for s in self.manifest.get("settings", [])}
            if params.get("key") not in keys:
                raise RuntimeError(f"«{params.get('key')}» no está en los ajustes de su manifiesto")
            return
        if method == "oauth.authorize":
            for key in ("authorize_url", "token_url"):
                self._need(self._host(str(params.get(key, "")), ("https",)))
            if not str(params.get("client_id", "")).strip():
                raise RuntimeError("falta el identificador de la app (client_id)")
            return
        if method == "open.uri":
            self._need("apps:launch")
            uri = str(params.get("uri", ""))
            scheme = uri.split(":", 1)[0].lower()
            if scheme == "https":
                self._need(self._host(uri, ("https",)))
            elif scheme not in APP_SCHEMES:
                raise RuntimeError(f"solo se pueden abrir {', '.join(sorted(APP_SCHEMES))}")
            return
        if method in ("net.fetch", "ws.open"):
            schemes = ("http", "https") if method == "net.fetch" else ("ws", "wss")
            needed = self._host(str(params.get("url", "")), schemes)
        elif method in _FILES:
            needed = f"files:{_FILES[method]}:{params.get('folder', '')}"
        elif method in _PLAIN:
            needed = _PLAIN[method]
        elif method in _SOCKET:
            return
        else:
            raise RuntimeError(f"Nyx no sabe hacer «{method}»")
        self._need(needed)

    def _need(self, permission: str) -> None:
        if permission not in self.permissions:
            raise PermissionDeniedError(f"sin permiso «{permission}»")

    @staticmethod
    def _host(url: str, schemes: tuple[str, ...]) -> str:
        """El permiso de red que hace falta para `url` (net:servidor:puerto)."""
        parts = urlsplit(url)
        if parts.scheme not in schemes or not parts.hostname:
            raise RuntimeError(f"dirección no válida: {url}")
        port = parts.port or (443 if parts.scheme in ("https", "wss") else 80)
        return f"net:{parts.hostname.lower()}:{port}"

    def _check_args(self, tool: str, args: dict[str, Any]) -> None:
        params = self.specs[tool].get("parameters") or {}
        props: dict[str, Any] = params.get("properties") or {}
        for name in params.get("required") or ():
            if name not in args:
                raise TypeError(f"«{tool}»: falta «{name}»")
        for name, value in args.items():
            prop = props.get(name)
            if prop is None:
                raise TypeError(f"«{tool}»: no tiene el parámetro «{name}»")
            kind = _JSON_TYPES[prop["type"]]
            if not isinstance(value, kind) or (
                prop["type"] != "boolean" and isinstance(value, bool)
            ):
                raise TypeError(f"«{tool}»: «{name}» tiene que ser {prop['type']}")
            if prop.get("enum") and value not in prop["enum"]:
                raise TypeError(f"«{tool}»: «{name}» tiene que ser uno de {prop['enum']}")
