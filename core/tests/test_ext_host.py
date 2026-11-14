"""Host de extensiones con código (7.06): llamadas, tiempos, caídas y desactivación.

Aquí las extensiones corren sin encerrar (con el Python de las pruebas) para probar el
protocolo y el host; el encierro de verdad se prueba en test_ext_sandbox.py.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path
from typing import IO, Any

import pytest

from nyx.ext.host import ExtensionCrashError, ExtensionHost
from nyx.ext.rpc import RpcError
from nyx.ext.runtime import RUNNER_SOURCE

TOOLS = """
import asyncio, os, sys, time
import nyx

@nyx.tool
def saluda(nombre: str) -> str:
    print("saludando a", nombre)
    return f"Hola, {nombre}"

@nyx.tool
async def suma(a: int, b: int) -> dict:
    await asyncio.sleep(0)
    return {"total": a + b}

@nyx.tool
def falla() -> None:
    raise ValueError("algo suyo")

@nyx.tool
def cuelga() -> None:
    time.sleep(60)

@nyx.tool
def muere() -> None:
    os._exit(7)

@nyx.tool
def basura() -> None:
    os.write(1, b"esto no es json\\n")
    time.sleep(5)

@nyx.tool
async def pide(metodo: str) -> object:
    return await nyx.ask(metodo, {"x": 1}, timeout_s=5)

@nyx.tool
def pide_sync(metodo: str) -> object:
    return nyx.ask_sync(metodo, {"x": 2}, timeout_s=5)
"""


class PlainProcess:
    """Un proceso sin encerrar con la misma forma que SandboxProcess (solo pruebas)."""

    def __init__(self, popen: subprocess.Popen[bytes]) -> None:
        self._p = popen
        self.pid = popen.pid
        assert popen.stdin is not None and popen.stdout is not None
        self.stdin: IO[bytes] = popen.stdin
        self.stdout: IO[bytes] = popen.stdout
        self.game_calls: list[bool] = []

    def poll(self) -> int | None:
        return self._p.poll()

    def wait(self, timeout: float) -> int | None:
        try:
            return self._p.wait(timeout)
        except subprocess.TimeoutExpired:
            return None

    def set_game(self, active: bool) -> None:
        self.game_calls.append(active)

    def kill(self) -> None:
        self._p.kill()
        self._p.wait()
        for pipe in (self.stdin, self.stdout):
            pipe.close()


class PlainLauncher:
    def __init__(self, data: Path) -> None:
        self.game = False
        self.data = data
        self.started: list[PlainProcess] = []

    def start(self, ext_id: str, package: Path) -> PlainProcess:
        popen = subprocess.Popen(
            [sys.executable, "-I", str(RUNNER_SOURCE), str(package), str(self.data)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        proc = PlainProcess(popen)
        self.started.append(proc)
        return proc


def make_package(root: Path, source: str = TOOLS) -> Path:
    (root / "tools").mkdir(parents=True)
    (root / "tools" / "main.py").write_text(textwrap.dedent(source), encoding="utf-8")
    return root


@pytest.fixture
def pkg(tmp_path: Path) -> Path:
    return make_package(tmp_path / "pkg")


@pytest.fixture
def launcher(tmp_path: Path) -> PlainLauncher:
    return PlainLauncher(tmp_path / "data")


async def test_calls_sync_and_async_tools(pkg: Path, launcher: PlainLauncher) -> None:
    host = ExtensionHost(launcher)
    try:
        assert await host.call("t.ext", pkg, "saluda", {"nombre": "Ana"}, 5) == "Hola, Ana"
        assert await host.call("t.ext", pkg, "suma", {"a": 2, "b": 3}, 5) == {"total": 5}
        assert set(host.tools("t.ext")) >= {"saluda", "suma", "falla"}
        assert len(launcher.started) == 1  # el mismo proceso para las dos
        # «print» va al registro, no rompe el protocolo.
        assert any("saludando a Ana" in line for line in host.logs["t.ext"])
    finally:
        await host.stop_all()


async def test_tool_error_is_not_a_crash(pkg: Path, launcher: PlainLauncher) -> None:
    host = ExtensionHost(launcher)
    try:
        with pytest.raises(RpcError, match="algo suyo"):
            await host.call("t.ext", pkg, "falla", {}, 5)
        with pytest.raises(RpcError, match="no tiene la herramienta"):
            await host.call("t.ext", pkg, "no_existe", {}, 5)
        assert host.crashes.get("t.ext") is None
        assert await host.call("t.ext", pkg, "saluda", {"nombre": "B"}, 5) == "Hola, B"
        assert len(launcher.started) == 1
    finally:
        await host.stop_all()


async def test_hang_is_killed_and_restarted(pkg: Path, launcher: PlainLauncher) -> None:
    host = ExtensionHost(launcher)
    try:
        with pytest.raises(ExtensionCrashError, match="tardó"):
            await host.call("t.ext", pkg, "cuelga", {}, 0.5)
        assert host.crashes["t.ext"] == 1
        assert launcher.started[0].poll() is not None  # matada
        assert await host.call("t.ext", pkg, "saluda", {"nombre": "C"}, 5) == "Hola, C"
        assert len(launcher.started) == 2
        assert "t.ext" not in host.crashes  # una que va bien pone la cuenta a cero
    finally:
        await host.stop_all()


async def test_three_crashes_disable(pkg: Path, launcher: PlainLauncher) -> None:
    disabled: list[tuple[str, str]] = []

    async def on_disabled(ext_id: str, reason: str) -> None:
        disabled.append((ext_id, reason))

    host = ExtensionHost(launcher, on_disabled=on_disabled)
    try:
        for _ in range(3):
            with pytest.raises(ExtensionCrashError):
                await host.call("t.ext", pkg, "muere", {}, 5)
        assert disabled and disabled[0][0] == "t.ext" and "3 veces" in disabled[0][1]
        with pytest.raises(ExtensionCrashError, match="3 veces"):
            await host.call("t.ext", pkg, "saluda", {"nombre": "D"}, 5)
        assert len(launcher.started) == 3  # desactivada: ya no se arranca
        host.enable("t.ext")
        assert await host.call("t.ext", pkg, "saluda", {"nombre": "D"}, 5) == "Hola, D"
    finally:
        await host.stop_all()


async def test_garbage_on_stdout_is_a_crash(pkg: Path, launcher: PlainLauncher) -> None:
    host = ExtensionHost(launcher)
    try:
        with pytest.raises(ExtensionCrashError, match="JSON"):
            await host.call("t.ext", pkg, "basura", {}, 5)
        assert host.crashes["t.ext"] == 1
    finally:
        await host.stop_all()


async def test_broken_extension_does_not_start(tmp_path: Path, launcher: PlainLauncher) -> None:
    pkg = make_package(tmp_path / "rota", "import modulo_que_no_existe\n")
    host = ExtensionHost(launcher)
    with pytest.raises(ExtensionCrashError, match="no carga: ModuleNotFoundError"):
        await host.call("t.rota", pkg, "x", {}, 5)
    assert host.crashes["t.rota"] == 1
    await host.stop_all()


async def test_extension_asks_nyx(pkg: Path, launcher: PlainLauncher) -> None:
    seen: list[dict[str, Any]] = []

    async def echo(params: dict[str, Any]) -> dict[str, Any]:
        seen.append(params)
        return {"ok": params["x"]}

    host = ExtensionHost(launcher, handlers=lambda ext_id: {"prueba.eco": echo})
    try:
        assert await host.call("t.ext", pkg, "pide", {"metodo": "prueba.eco"}, 5) == {"ok": 1}
        assert await host.call("t.ext", pkg, "pide_sync", {"metodo": "prueba.eco"}, 5) == {"ok": 2}
        assert seen == [{"x": 1}, {"x": 2}]
        # Lo que Nyx no conoce, o lo que no se le deja (7.07), le llega como error.
        with pytest.raises(RpcError, match="Nyx no conoce"):
            await host.call("t.ext", pkg, "pide", {"metodo": "files.read"}, 5)
    finally:
        await host.stop_all()


async def test_game_mode_reaches_running_processes(pkg: Path, launcher: PlainLauncher) -> None:
    host = ExtensionHost(launcher)
    try:
        await host.call("t.ext", pkg, "saluda", {"nombre": "E"}, 5)
        host.set_game(True)
        host.set_game(False)
        assert launcher.started[0].game_calls == [True, False]
        assert launcher.game is False
    finally:
        await host.stop_all()


async def test_idle_extension_is_stopped(pkg: Path, launcher: PlainLauncher) -> None:
    host = ExtensionHost(launcher, idle_stop=0.2)
    await host.call("t.ext", pkg, "saluda", {"nombre": "F"}, 5)
    proc = launcher.started[0]
    for _ in range(40):
        if proc.poll() is not None:
            break
        import asyncio

        await asyncio.sleep(0.1)
    assert proc.poll() is not None
    assert host.tools("t.ext") == ()
    # Vuelve a arrancar sola al llamarla.
    assert await host.call("t.ext", pkg, "saluda", {"nombre": "G"}, 5) == "Hola, G"
    await host.stop_all()
