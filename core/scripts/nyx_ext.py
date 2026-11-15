"""Herramienta para hacer extensiones de Nyx (tareas 7.12 y 7.13: docs/extensiones/README.md).

    uv run python scripts/nyx_ext.py new carpeta --id autor.nombre --tipo tools
        Crea una extensión de ejemplo del tipo pedido (tools, actions, knowledge, preset,
        personality o shape). Nunca sobrescribe nada.
    uv run python scripts/nyx_ext.py validate carpeta
        Comprueba el manifiesto, el contenido y `tools/tools.json` como lo haría Nyx al
        instalarla.
    uv run python scripts/nyx_ext.py run carpeta herramienta [--args '{"a": 1}']
        Prueba una herramienta como en Nyx: encerrada y con lo que pida a Nyx de verdad (red,
        secretos...), con los permisos del manifiesto. `--sin-aislar` la corre con el Python de
        aquí (para depurar; nunca con código que no sea tuyo).
    uv run python scripts/nyx_ext.py pack carpeta [-o salida.nyxext]
        La empaqueta (si valida) en un .nyxext listo para firmar (`sign_extension.py`) o para
        instalar en modo desarrollador.

Para las pruebas con pytest, sin Nyx: `nyx_sdk.testing.FakeNyx` (sdk/, MIT).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import IO, Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nyx.ext.content import load_content
from nyx.ext.manifest import MANIFEST_NAME, Manifest, ManifestError, load_manifest
from nyx.ext.official import SKIP, pack_folder
from nyx.ext.store import PackageError, check_code
from nyx.ext.tools_spec import TOOLS_FILE, load_tools
from nyx.paths import local_dir

TOOLS_MAIN = '''"""Herramientas de la extensión.

Nyx las corre encerradas (sin red, sin tus archivos): lo que necesiten de fuera se lo piden a
Nyx con `nyx.ask`, y Nyx solo lo hace si el permiso está en el manifiesto y el usuario lo ha
aceptado. Lo que devuelven, Nyx se lo dice al usuario.
"""

import nyx


@nyx.tool
async def saluda(nombre: str) -> str:
    await nyx.ask("notify", {"title": "Hola", "text": f"Saludos a {nombre}"})
    return f"Le he mandado un saludo a {nombre}."
'''

TOOLS_TEST = '''"""Pruebas sin Nyx (`uv add --dev nyx-sdk pytest`, o el sdk/ del repositorio)."""

from pathlib import Path

from nyx_sdk.testing import FakeNyx

FOLDER = Path(__file__).resolve().parents[1]


def test_saluda() -> None:
    nyx = FakeNyx(FOLDER)
    nyx.answer("notify", None)
    assert nyx.run("saluda", nombre="Ana") == "Le he mandado un saludo a Ana."
    assert nyx.asked("notify") == [{"title": "Hola", "text": "Saludos a Ana"}]
'''

EXAMPLES: dict[str, dict[str, object]] = {
    "tools": {
        "tools/main.py": TOOLS_MAIN,
        "tools/tools.json": [
            {
                "name": "saluda",
                "description": "Manda un saludo a alguien.",
                "parameters": {
                    "properties": {"nombre": {"type": "string", "description": "A quién"}},
                    "required": ["nombre"],
                },
                "risk": "green",
                "uses": ["notify"],
                "game_policy": "allowed",
            }
        ],
        "tests/test_main.py": TOOLS_TEST,
    },
    "knowledge": {
        "knowledge/guia.md": "# Guía\n\n## Primeros pasos\n\nCuenta aquí lo que Nyx debe saber.\n"
    },
    "actions": {
        "actions.json": {
            "apps": [
                {
                    "name": "Mi app",
                    "processes": ["miapp.exe"],
                    "names": ["mi app"],
                    "actions": {
                        "save": {"label": "Guardar", "keys": {"es": "ctrl+g", "en": "ctrl+s"}}
                    },
                }
            ]
        }
    },
    "preset": {
        "presets/tranquila.json": {
            "name": "Tranquila",
            "description": "Habla más despacio y en tono neutro.",
            "settings": {"tts": {"speed": 0.9}, "responses": {"tone": "neutro"}},
        }
    },
    "personality": {
        "personality.json": {
            "name": "Mi personalidad",
            "tone": "divertido",
            "phrases": {"thanks": ["¡A mandar!", "¡Para eso estoy!"]},
        }
    },
    "shape": {
        "shape/shape.json": {"name": "Círculo", "box": 1.0},
        "shape/shape.glsl": (
            "void main() {\n"
            "  vec2 p = gl_FragCoord.xy - nyx_resolution * 0.5;\n"
            "  float d = length(p) - nyx_size * 0.42 * nyx_appear * (1.0 + 0.08 * nyx_audio);\n"
            "  float a = clamp(0.5 - d, 0.0, 1.0);\n"
            "  gl_FragColor = vec4(nyx_color * a, a);\n"
            "}\n"
        ),
    },
}


def new(folder: Path, ext_id: str, kind: str) -> None:
    if folder.exists() and any(folder.iterdir()):
        sys.exit(f"{folder} no está vacía: no sobrescribo nada")
    manifest: dict[str, object] = {
        "id": ext_id,
        "name": ext_id.split(".", 1)[-1].replace("-", " ").capitalize(),
        "version": "0.1.0",
        "author": ext_id.split(".", 1)[0],
        "description": "",
        "nyx_api": ">=1.0 <2.0",
        "kinds": [kind],
        "license": {"type": "free", "spdx": "MIT"},
    }
    if kind == "tools":
        manifest["permissions"] = ["notify"]
        manifest["groups"] = [
            {
                "name": "saludos",
                "about": "Mandar saludos",
                "keywords": ["saluda", "saludo"],
                "tools": ["saluda"],
            }
        ]
    files: dict[str, object] = {MANIFEST_NAME: manifest, **EXAMPLES[kind]}
    for rel, content in files.items():
        path = folder / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        text = (
            content
            if isinstance(content, str)
            else json.dumps(content, ensure_ascii=False, indent=2) + "\n"
        )
        with open(path, "x", encoding="utf-8", newline="\n") as f:
            f.write(text)
    print(f"Creada en {folder}. Cámbiala y comprueba con: validate {folder}")


def validate(folder: Path) -> bool:
    try:
        manifest = load_manifest((folder / MANIFEST_NAME).read_bytes())
    except (OSError, ManifestError) as e:
        print(f"Manifiesto: {e}")
        return False
    content = load_content(manifest, folder)
    problems = list(content.problems)
    if "tools" in manifest.kinds:
        try:
            check_code(folder, manifest)
        except PackageError as e:
            problems.append(str(e))
    for problem in problems:
        print(f"Problema: {problem}")
    if not problems:
        print(f"Bien: {manifest.id} {manifest.version} ({', '.join(manifest.kinds)})")
    return not problems


def run(
    folder: Path,
    tool: str,
    args: dict[str, Any],
    *,
    isolated: bool,
    settings: dict[str, str] | None = None,
) -> None:
    """Llama a una herramienta como Nyx, con los permisos del manifiesto ya aceptados."""
    if not validate(folder):
        sys.exit("No se prueba: arregla lo de arriba")
    manifest = load_manifest((folder / MANIFEST_NAME).read_bytes())
    specs = {s.name: s for s in load_tools((folder / TOOLS_FILE).read_bytes(), manifest)}
    if tool not in specs:
        sys.exit(f"«{tool}» no está en {TOOLS_FILE} (hay: {', '.join(sorted(specs))})")
    asyncio.run(_run(folder, manifest, tool, args, isolated=isolated, settings=settings or {}))


async def _run(
    folder: Path,
    manifest: Manifest,
    tool: str,
    args: dict[str, Any],
    *,
    isolated: bool,
    settings: dict[str, str],
) -> None:
    from nyx.bus import EventBus
    from nyx.events import BubbleShown
    from nyx.ext.api import ExtensionApi
    from nyx.ext.host import ExtensionHost, Launcher
    from nyx.ext.rpc import RpcError

    bus = EventBus()

    async def show(event: BubbleShown) -> None:
        print(f"[aviso] {event.display}" + (f" · {event.secondary}" if event.secondary else ""))

    bus.subscribe(BubbleShown, show)
    from nyx.ext.api import read_setting

    def setting(ext_id: str, key: str) -> str | None:
        # Los de `--ajuste`; si no, los guardados en Ajustes (si la tienes instalada).
        return settings[key] if key in settings else read_setting(ext_id, key)

    api = ExtensionApi(
        bus,
        lambda _id: tuple(manifest.permissions),
        settings_of=lambda _id: tuple(s.key for s in manifest.settings),
        setting_reader=setting,
    )
    launcher: Launcher
    if isolated:
        from nyx.ext.sandbox import SandboxLauncher

        # Una copia: encerrarla cambia los permisos de su carpeta, y la tuya no se toca.
        package = local_dir() / "ext-dev" / manifest.id
        shutil.copytree(folder, package, dirs_exist_ok=True, ignore=shutil.ignore_patterns(*SKIP))
        launcher = SandboxLauncher()
    else:
        print("Aviso: sin aislar, con el Python de aquí. Solo para depurar tu propio código.")
        package, launcher = folder, _PlainLauncher(local_dir() / "ext-dev" / "datos")
    host = ExtensionHost(launcher, handlers=api.handlers)
    try:
        result = await host.call(manifest.id, package, tool, args, timeout_s=20.0)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except RpcError as e:
        print(f"La herramienta ha fallado: {e}")
    finally:
        for line in host.logs.get(manifest.id, []):
            print(f"[log] {line}")
        await host.stop_all()
        await api.close(manifest.id)


class _PlainProcess:
    """Sin encerrar (solo `--sin-aislar`): la misma forma que SandboxProcess."""

    def __init__(self, popen: subprocess.Popen[bytes]) -> None:
        assert popen.stdin is not None and popen.stdout is not None
        self._p = popen
        self.pid = popen.pid
        self.stdin: IO[bytes] = popen.stdin
        self.stdout: IO[bytes] = popen.stdout

    def poll(self) -> int | None:
        return self._p.poll()

    def wait(self, timeout: float) -> int | None:
        try:
            return self._p.wait(timeout)
        except subprocess.TimeoutExpired:
            return None

    def set_game(self, active: bool) -> None:
        pass

    def kill(self) -> None:
        self._p.kill()
        self._p.wait()


class _PlainLauncher:
    def __init__(self, data: Path) -> None:
        self.game = False
        self.data = data

    def start(self, ext_id: str, package: Path) -> _PlainProcess:
        from nyx.ext.runtime import RUNNER_SOURCE

        self.data.mkdir(parents=True, exist_ok=True)
        popen = subprocess.Popen(
            [sys.executable, "-I", str(RUNNER_SOURCE), str(package), str(self.data)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        return _PlainProcess(popen)


def pack(folder: Path, out: Path | None) -> None:
    if not validate(folder):
        sys.exit("No se empaqueta: arregla lo de arriba")
    manifest = load_manifest((folder / MANIFEST_NAME).read_bytes())
    out = out or folder.parent / f"{manifest.id}-{manifest.version}.nyxext"
    try:
        pack_folder(folder, out)
    except PackageError as e:
        sys.exit(f"El paquete no valdría: {e}")
    print(f"Empaquetada en {out} (sin firmar: para instalarla sin firma, modo desarrollador)")


def main() -> None:
    # En una consola o tubería que no es UTF-8, «→» o «ñ» no deben tumbar la herramienta.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_new = sub.add_parser("new")
    p_new.add_argument("carpeta", type=Path)
    p_new.add_argument("--id", required=True, help="autor.nombre (minúsculas)")
    p_new.add_argument("--tipo", choices=sorted(EXAMPLES), default="knowledge")
    sub.add_parser("validate").add_argument("carpeta", type=Path)
    p_run = sub.add_parser("run")
    p_run.add_argument("carpeta", type=Path)
    p_run.add_argument("herramienta")
    p_run.add_argument("--args", default="{}", help="los argumentos, en JSON")
    p_run.add_argument("--sin-aislar", action="store_true")
    p_run.add_argument("--ajuste", action="append", default=[], help="clave=valor (sus «settings»)")
    p_pack = sub.add_parser("pack")
    p_pack.add_argument("carpeta", type=Path)
    p_pack.add_argument("-o", "--salida", type=Path)
    args = parser.parse_args()
    if args.cmd == "new":
        new(args.carpeta, args.id, args.tipo)
    elif args.cmd == "validate":
        sys.exit(0 if validate(args.carpeta) else 1)
    elif args.cmd == "run":
        tool_args = json.loads(args.args)
        if not isinstance(tool_args, dict):
            sys.exit("--args tiene que ser un objeto JSON")
        pairs = dict(a.split("=", 1) for a in args.ajuste if "=" in a)
        run(
            args.carpeta,
            args.herramienta,
            tool_args,
            isolated=not args.sin_aislar,
            settings=pairs,
        )
    else:
        pack(args.carpeta, args.salida)


if __name__ == "__main__":
    main()
