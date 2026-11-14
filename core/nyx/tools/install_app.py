"""install_app: instalar o desinstalar programas con winget (0.6, tarea 6.14).

- **Roja siempre** y bloqueada en partida. Antes de confirmar se busca con winget y la
  confirmación enseña el nombre exacto, el editor y el identificador: se instala exactamente
  eso (`--id <id> -e`), nunca «lo primero que salga».
- Si hay varias coincidencias y ninguna se llama igual, no se adivina: se dicen las opciones.
- `--silent --accept-package-agreements --accept-source-agreements`, nunca `--force`. Si el
  instalador pide administrador, lo pide Windows (Nyx nunca se eleva).
- Desinstalar quita un programa (no es borrar archivos del usuario, que irían a la papelera):
  por eso también es roja y se confirma con el nombre exacto.
"""

from __future__ import annotations

import asyncio
import logging
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pydantic import Field

from nyx.index.aliases import normalize
from nyx.tools.base import (
    Category,
    GamePolicy,
    Params,
    Prepared,
    Risk,
    Tool,
    ToolContext,
    ToolResult,
)

log = logging.getLogger(__name__)

Action = Literal["install", "uninstall"]
SEARCH_TIMEOUT_S = 30.0
INSTALL_TIMEOUT_S = 15 * 60.0
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_AGREE = ["--accept-source-agreements"]


@dataclass(frozen=True, slots=True)
class Package:
    name: str
    id: str
    version: str = ""


def winget(args: list[str], timeout_s: float = SEARCH_TIMEOUT_S) -> tuple[int, str]:
    """Ejecuta winget y devuelve (código, salida)."""
    res = subprocess.run(
        ["winget", *args],
        capture_output=True,
        timeout=timeout_s,
        creationflags=_NO_WINDOW,
        check=False,
    )
    return res.returncode, res.stdout.decode("utf-8", errors="replace")


def parse_table(output: str) -> list[Package]:
    """Filas de la tabla de `winget search` / `winget list` (en cualquier idioma): las
    columnas empiezan donde empiezan los títulos de la cabecera, encima de la línea de guiones."""
    lines = [ln.rstrip() for chunk in output.splitlines() for ln in chunk.split("\r")]
    dash = next((i for i, ln in enumerate(lines) if re.fullmatch(r"-{10,}", ln.strip())), None)
    if dash is None or dash == 0:
        return []
    header = lines[dash - 1]
    starts = [m.start() for m in re.finditer(r"\S+", header)]
    if len(starts) < 2:
        return []
    out: list[Package] = []
    for line in lines[dash + 1 :]:
        if not line.strip() or len(line) < starts[1]:
            continue
        cols = [
            line[a:b].strip() for a, b in zip(starts, [*starts[1:], len(line) + 1], strict=False)
        ]
        name, pkg_id = cols[0], cols[1].split()[0] if cols[1] else ""
        if name and pkg_id:
            out.append(Package(name, pkg_id, cols[2] if len(cols) > 2 else ""))
    return out


def publisher(show_output: str) -> str:
    """El editor que dice `winget show` («Editor:» en español, «Publisher:» en inglés)."""
    m = re.search(r"^(?:Editor|Publisher):\s*(.+)$", show_output, re.MULTILINE)
    return m.group(1).strip() if m else ""


def choose(packages: list[Package], query: str) -> Package | list[Package] | None:
    """El paquete que se llama como lo pedido; si no hay uno claro, las opciones."""
    if not packages:
        return None
    wanted = normalize(query)
    exact = [p for p in packages if normalize(p.name) == wanted or normalize(p.id) == wanted]
    if len(exact) == 1:
        return exact[0]
    if len(packages) == 1:
        return packages[0]
    return exact or packages[:3]


class InstallAppParams(Params):
    action: Action = Field(description="install o uninstall")
    name: str = Field(min_length=2, max_length=80, description="Nombre del programa")


class InstallApp(Tool[InstallAppParams]):
    name = "install_app"
    description = (
        "Instala o desinstala un programa con winget, siempre con confirmación. "
        "Ej.: «instala VLC» (action=install, name=VLC), «desinstala Zoom» (action=uninstall)."
    )
    risk = Risk.RED
    game_policy = GamePolicy.BLOCKED
    category = Category.APPS
    params_model = InstallAppParams
    timeout_s = INSTALL_TIMEOUT_S + 2 * SEARCH_TIMEOUT_S

    def __init__(self, runner: Callable[..., tuple[int, str]] = winget) -> None:
        self._run = runner

    async def prepare(self, params: InstallAppParams, ctx: ToolContext) -> Prepared:
        verb = "Instalar" if params.action == "install" else "Desinstalar"
        lookup = (
            ["search", "--name", params.name, *_AGREE]
            if params.action == "install"
            else ["list", "--name", params.name, *_AGREE]
        )
        try:
            _, out = await asyncio.to_thread(self._run, lookup)
        except OSError, subprocess.TimeoutExpired:
            log.warning("winget no responde", exc_info=True)
            return Prepared(
                summary=verb,
                error=ToolResult.fail("No he podido usar winget", "¿está instalado?"),
            )
        found = choose(parse_table(out), params.name)
        if found is None:
            where = "para instalar" if params.action == "install" else "instalado"
            return Prepared(
                summary=verb,
                error=ToolResult.fail(f"No encuentro «{params.name}» {where}"),
            )
        if isinstance(found, list):
            options = ", ".join(p.name for p in found)
            return Prepared(
                summary=verb,
                error=ToolResult.fail("Hay varios con ese nombre", f"¿Cuál? {options}"),
            )
        editor = ""
        if params.action == "install":
            try:
                _, shown = await asyncio.to_thread(
                    self._run, ["show", "--id", found.id, "-e", *_AGREE]
                )
                editor = publisher(shown)
            except OSError, subprocess.TimeoutExpired:
                editor = ""
        detail = " · ".join(p for p in (editor, found.id, found.version) if p)
        return Prepared(summary=f"{verb} {found.name}", detail=detail, risk=Risk.RED, payload=found)

    async def execute(
        self, params: InstallAppParams, ctx: ToolContext, prepared: Prepared
    ) -> ToolResult:
        pkg = prepared.payload
        assert isinstance(pkg, Package)
        args = [params.action, "--id", pkg.id, "-e", "--silent", *_AGREE]
        if params.action == "install":
            args.append("--accept-package-agreements")
        try:
            code, out = await asyncio.to_thread(self._run, args, INSTALL_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            return ToolResult.fail("La instalación tarda demasiado", "mírala en winget")
        except OSError:
            return ToolResult.fail("No he podido usar winget")
        done = "Instalado" if params.action == "install" else "Desinstalado"
        if code != 0:
            log.warning("winget %s %s → %s: %s", params.action, pkg.id, code, out[-400:])
            what = "instalar" if params.action == "install" else "desinstalar"
            return ToolResult.fail(f"No he podido {what} {pkg.name}", "winget ha dado un error")
        return ToolResult(
            ok=True,
            message=f"{done} {pkg.name}.",
            display=f"{done} {pkg.name}",
            data={"action": params.action, "id": pkg.id},
        )
