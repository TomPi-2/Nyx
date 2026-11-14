"""El encierro de verdad (7.06): una extensión que intenta salirse no puede.

Necesita Windows y el Python de las extensiones ya descargado (`runtime.ensure_python()`; no
se descarga en las pruebas). Crea AppContainers y escritorios de prueba y los borra al acabar.
"""

from __future__ import annotations

import contextlib
import os
import socket
import sys
import threading
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from nyx.ext import runtime

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or not (runtime.python_dir() / "python.exe").exists(),
    reason="sin Windows o sin el Python de las extensiones",
)

TOOLS = """
import os, socket, subprocess, sys
import nyx

@nyx.tool
def leer(ruta: str) -> str:
    with open(ruta, encoding="utf-8") as f:
        return f.read()

@nyx.tool
def escribir_mio(texto: str) -> str:
    ruta = nyx.data_dir / "nota.txt"
    ruta.write_text(texto, encoding="utf-8")
    return ruta.read_text(encoding="utf-8")

@nyx.tool
def conectar(puerto: int) -> str:
    socket.create_connection(("127.0.0.1", puerto), timeout=2).close()
    return "conectado"

@nyx.tool
def lanzar() -> str:
    return subprocess.run(["cmd", "/c", "echo hola"], capture_output=True, text=True).stdout

@nyx.tool
def entorno() -> list:
    return sorted(os.environ)

@nyx.tool
def memoria(mb: int) -> int:
    return len(bytearray(mb * 1024 * 1024))

@nyx.tool
def version() -> str:
    return sys.version.split()[0]
"""


@pytest.fixture
async def setup(tmp_path: Path) -> AsyncIterator[tuple[object, Path, str]]:
    from nyx.ext.host import ExtensionHost
    from nyx.ext.sandbox import Limits, SandboxLauncher, delete_container

    package = tmp_path / "pkg"
    (package / "tools").mkdir(parents=True)
    (package / "tools" / "main.py").write_text(TOOLS, encoding="utf-8")
    ext_id = f"pruebas.sandbox-{uuid.uuid4().hex[:8]}"
    launcher = SandboxLauncher(Limits(memory_mb=128), data_root=tmp_path / "datos")
    host = ExtensionHost(launcher)
    yield host, package, ext_id
    await host.stop_all()
    delete_container(ext_id)


async def test_isolated_extension_cannot_escape(
    setup: tuple[object, Path, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nyx.ext.host import ExtensionHost
    from nyx.ext.rpc import RpcError

    host, package, ext_id = setup
    assert isinstance(host, ExtensionHost)
    secret = tmp_path / "usuario" / "secreto.txt"
    secret.parent.mkdir()
    secret.write_text("privado", encoding="utf-8")
    monkeypatch.setenv("NYX_PRUEBA_CLAVE", "no-debe-verse")

    async def call(tool: str, **args: object) -> object:
        return await host.call(ext_id, package, tool, dict(args), 20)

    assert await call("version") == runtime.PYTHON_VERSION
    # Su carpeta de datos, sí.
    assert await call("escribir_mio", texto="hola") == "hola"
    # Los archivos del usuario, no.
    with pytest.raises(RpcError, match="PermissionError"):
        await call("leer", ruta=str(secret))
    # Ni la red (ni siquiera el propio PC).
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()

    def accept() -> None:
        with contextlib.suppress(OSError):  # se cierra al acabar
            server.accept()

    threading.Thread(target=accept, daemon=True).start()
    try:
        with pytest.raises(RpcError, match="Error"):
            await call("conectar", puerto=server.getsockname()[1])
    finally:
        server.close()
    # Ni lanzar otros programas (el job solo deja un proceso).
    with pytest.raises(RpcError):
        await call("lanzar")
    # Ni ve las variables de Nyx ni las del usuario.
    names = await call("entorno")
    assert isinstance(names, list)
    assert "NYX_PRUEBA_CLAVE" not in names and "PATH" not in names
    # Ni pasarse de memoria.
    with pytest.raises(RpcError, match="MemoryError"):
        await call("memoria", mb=400)
    # En partida baja de prioridad sin cortar nada.
    host.set_game(True)
    assert await call("version") == runtime.PYTHON_VERSION
    host.set_game(False)
    assert host.crashes.get(ext_id) is None


def test_container_names_fit() -> None:
    from nyx.ext.sandbox import container_name, desktop_name

    long_id = "a" * 32 + "." + "b" * 48
    assert len(container_name(long_id)) <= 64
    assert container_name(long_id) != container_name("otro.id")
    assert "\\" not in desktop_name(long_id)
    assert os.sep not in container_name(long_id)
