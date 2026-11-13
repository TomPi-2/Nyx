"""run_powershell: el comodín para lo que no cubre ninguna otra herramienta (0.6, tarea 6.13).

SPEC §7 y §8:

- **Roja siempre.** La confirmación enseña el comando exacto, y se ejecuta exactamente eso.
  (El plan de la 0.6 proponía una excepción verde para órdenes de solo lectura; la SPEC dice
  «rojo siempre» y no se bajan los niveles de seguridad: queda como decisión del usuario.)
- **Lista de bloqueo** comprobada con el analizador de PowerShell
  (`System.Management.Automation.Language.Parser`), no con el texto: así un alias (`rm`, `iex`),
  una orden dentro de un bloque o una llamada .NET no se cuelan. Se bloquea: borrar sin
  papelera, formatear y tocar discos o el arranque, el registro, políticas de ejecución y de
  Defender, el cortafuegos, servicios y tareas programadas, desinstalar, descargar y ejecutar
  código de fuera (`iwr | iex`, `Invoke-Expression`, `Add-Type`, WebClient…), elevarse
  (`Start-Process -Verb RunAs`), apagar o reiniciar (para eso está `system_power`), lanzar
  otros intérpretes (`cmd`, `powershell -EncodedCommand`…) y cualquier orden cuyo nombre no se
  sepa antes de ejecutarla (`& $x`).
- Bloqueada en partida. `-NoProfile -NonInteractive`, 20 s como mucho y la salida recortada.
- Lo que devuelve es contenido de fuera (puede leer archivos o webs): va al LLM marcado como
  información, nunca como órdenes (`ToolResult.external`).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import Field

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

RUN_TIMEOUT_S = 20.0
PARSE_TIMEOUT_S = 10.0
MAX_OUTPUT = 1500
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_PS = ["powershell.exe", "-NoProfile", "-NonInteractive"]

# Analizador: lee el código (base64 en una variable de entorno, sin problemas de comillas) y
# devuelve en JSON lo que de verdad hay dentro, también en bloques anidados.
_ANALYZER = r"""
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$code = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($env:NYX_PS_CODE))
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseInput(
  $code, [ref]$tokens, [ref]$errors)
$ns = 'System.Management.Automation.Language.'
function Find($name) {
  $t = [type]($ns + $name)
  # GetNewClosure: el filtro lo llama .NET y, sin ella, no vería $t.
  @($ast.FindAll({ param($n) $n -is $t }.GetNewClosure(), $true))
}
$cmds = Find 'CommandAst'
$typeNames = @(Find 'TypeExpressionAst') + @(Find 'TypeConstraintAst')
[pscustomobject]@{
  commands = @($cmds | ForEach-Object { $_.GetCommandName() })
  dynamic = @($cmds | Where-Object { $null -eq $_.GetCommandName() }).Count
  params = @(Find 'CommandParameterAst' | ForEach-Object { $_.ParameterName })
  types = @($typeNames | ForEach-Object { $_.TypeName.FullName })
  members = @(Find 'InvokeMemberExpressionAst' | ForEach-Object { $_.Member.Extent.Text })
  redirects = @(Find 'FileRedirectionAst').Count
  assignments = @(Find 'AssignmentStatementAst').Count
  strings = @(Find 'StringConstantExpressionAst' | ForEach-Object { $_.Value })
  errors = @($errors | ForEach-Object { "$($_.Message)" })
  ok = ($null -ne $ast)
} | ConvertTo-Json -Compress
"""


@dataclass(frozen=True, slots=True)
class Analysis:
    """Lo que hay dentro del comando, según el analizador de PowerShell."""

    commands: list[str] = field(default_factory=list)
    dynamic: int = 0  # órdenes cuyo nombre no se sabe hasta ejecutarlas (`& $x`)
    params: list[str] = field(default_factory=list)
    types: list[str] = field(default_factory=list)
    members: list[str] = field(default_factory=list)
    strings: list[str] = field(default_factory=list)
    redirects: int = 0  # «> archivo»: escribe (y machaca) un archivo
    assignments: int = 0  # «$x = …»
    errors: list[str] = field(default_factory=list)


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    return [str(value)]


def analyze(code: str) -> Analysis:
    """Analiza `code` con el analizador de PowerShell (no lo ejecuta)."""
    env = {"NYX_PS_CODE": base64.b64encode(code.encode("utf-8")).decode("ascii")}
    res = subprocess.run(
        [*_PS, "-Command", _ANALYZER],
        capture_output=True,
        timeout=PARSE_TIMEOUT_S,
        env={**os.environ, **env},
        creationflags=_NO_WINDOW,
        check=False,
    )
    # Sin un análisis completo no se ejecuta nada: un fallo del analizador nunca deja pasar
    # el comando (antes, una salida vacía daba una lista vacía y todo pasaba).
    data = json.loads(res.stdout.decode("utf-8", errors="replace"))
    if not isinstance(data, dict) or data.get("ok") is not True or res.stderr.strip():
        raise ValueError(f"análisis incompleto: {res.stderr.decode('utf-8', 'replace')[:200]}")
    return Analysis(
        commands=_as_list(data.get("commands")),
        dynamic=int(data.get("dynamic") or 0),
        params=_as_list(data.get("params")),
        types=_as_list(data.get("types")),
        members=_as_list(data.get("members")),
        strings=_as_list(data.get("strings")),
        redirects=int(data.get("redirects") or 0),
        assignments=int(data.get("assignments") or 0),
        errors=_as_list(data.get("errors")),
    )


# --- lista de bloqueo (en minúsculas; los alias de PowerShell, con su orden) ---

_BLOCKED: dict[str, str] = {}


def _block(reason: str, *names: str) -> None:
    for name in names:
        _BLOCKED[name] = reason


_block(
    "borra sin pasar por la papelera",
    "remove-item", "rm", "del", "erase", "rd", "rmdir", "ri", "clear-content", "clc",
    "clear-item", "cli", "clear-recyclebin", "sdelete", "cipher",
)  # fmt: skip
_block(
    "escribe encima de archivos (se perdería lo que había, sin papelera)",
    "set-content", "out-file", "tee-object", "tee", "sc",
)  # fmt: skip
_block(
    "toca discos, particiones o el arranque",
    "format-volume", "clear-disk", "initialize-disk", "set-disk", "new-partition",
    "remove-partition", "resize-partition", "set-partition", "diskpart", "format", "bcdedit",
    "bootrec", "vssadmin", "wbadmin", "mountvol", "fsutil", "chkdsk", "repair-volume",
)  # fmt: skip
_block(
    "cambia el registro de Windows",
    "set-itemproperty", "sp", "new-itemproperty", "remove-itemproperty", "rp",
    "rename-itemproperty", "reg", "regedit", "regini",
)  # fmt: skip
_block(
    "cambia políticas de seguridad o el cortafuegos",
    "set-executionpolicy", "set-mppreference", "add-mppreference", "remove-mppreference",
    "set-netfirewallprofile", "new-netfirewallrule", "set-netfirewallrule", "netsh",
    "set-acl", "takeown", "icacls", "cacls", "secedit", "auditpol", "bitsadmin", "certutil",
)  # fmt: skip
_block(
    "toca servicios, tareas programadas o el inicio",
    "new-service", "set-service", "remove-service", "sc", "schtasks",
    "register-scheduledtask", "set-scheduledtask", "unregister-scheduledtask",
    "new-scheduledtask", "new-scheduledtaskaction",
)  # fmt: skip
_block(
    "desinstala o instala programas (para eso está install_app, con confirmación)",
    "winget", "msiexec", "wmic", "choco", "scoop", "install-package", "uninstall-package",
    "install-module", "uninstall-module", "remove-appxpackage", "add-appxpackage",
    "enable-windowsoptionalfeature", "disable-windowsoptionalfeature",
)  # fmt: skip
_block(
    "descarga o ejecuta código de fuera",
    "invoke-expression", "iex", "invoke-webrequest", "iwr", "curl", "wget",
    "invoke-restmethod", "irm", "start-bitstransfer", "invoke-command", "icm",
    "enter-pssession", "new-pssession", "add-type", "set-alias", "new-alias", "sal", "nal",
    "import-module", "ipmo",
)  # fmt: skip
_block(
    "lanza otro intérprete (podría esconder lo que hace)",
    "powershell", "powershell.exe", "pwsh", "pwsh.exe", "cmd", "cmd.exe", "wscript", "cscript",
    "mshta", "rundll32", "regsvr32", "bash", "wsl", "runas",
)  # fmt: skip
_block(
    "apaga o reinicia el equipo (para eso está system_power, con confirmación)",
    "stop-computer", "restart-computer", "shutdown", "shutdown.exe",
)  # fmt: skip

# Familias enteras: cualquier orden que empiece así.
_BLOCKED_PREFIXES = {
    "remove-": "borra o quita algo de Windows",
    "uninstall-": "desinstala algo",
    "unregister-": "quita algo registrado en Windows",
    "disable-": "desactiva algo de Windows",
    "clear-": "borra algo",
    "format-volume": "formatea un disco",
}
_BLOCKED_PARAMS = {"encodedcommand": "lleva código escondido"}
# Con -Force estas machacan lo que haya en el destino.
_OVERWRITERS = {"copy-item", "cpi", "cp", "copy", "move-item", "mi", "mv", "move", "new-item",
                "ni", "rename-item", "rni", "ren"}  # fmt: skip
_BLOCKED_TYPES = re.compile(
    r"net\.webclient|net\.http|reflection|interopservices|diagnostics\.process|io\.file|"
    r"io\.directory|microsoft\.win32|management\.automation\.powershell|activator",
    re.I,
)
_BLOCKED_MEMBERS = re.compile(
    r"^(?:delete|downloadstring|downloadfile|downloaddata|start|invoke|load|loadfrom|"
    r"createinstance|setvalue|deletevalue|deletesubkey|kill)$",
    re.I,
)
_REGISTRY = re.compile(r"^(?:hk(?:lm|cu|cr|u|cc)|registry)::?|^hkey_", re.I)


def blocked(analysis: Analysis) -> str | None:
    """Por qué no se ejecuta (para decírselo al usuario), o None si pasa la lista."""
    if analysis.errors:
        return "no es un comando válido de PowerShell"
    if analysis.dynamic:
        return "no se sabe qué orden ejecuta hasta lanzarlo"
    if analysis.redirects:
        return "escribe en un archivo con «>» (podría machacar uno, sin papelera)"
    names = [re.split(r"[\\/]", raw.strip().lower())[-1] for raw in analysis.commands]
    if any(p.lower() == "force" for p in analysis.params) and _OVERWRITERS & set(names):
        return "con -Force machaca lo que haya en el destino"
    for name in names:
        if name in _BLOCKED:
            return _BLOCKED[name]
        for prefix, reason in _BLOCKED_PREFIXES.items():
            if name.startswith(prefix):
                return reason
    if any(s.strip().lower() == "runas" for s in analysis.strings) and any(
        p.lower() == "verb" for p in analysis.params
    ):
        return "pide permisos de administrador"
    for param in analysis.params:
        if param.lower() in _BLOCKED_PARAMS:
            return _BLOCKED_PARAMS[param.lower()]
    if any(_BLOCKED_TYPES.search(t) for t in analysis.types):
        return "usa piezas de .NET que pueden hacer cualquier cosa"
    if any(_BLOCKED_MEMBERS.match(m.strip()) for m in analysis.members):
        return "llama a algo que puede borrar, descargar o ejecutar"
    if any(_REGISTRY.match(s.strip()) for s in analysis.strings):
        return "toca el registro de Windows"
    return None


# --- excepción verde: solo lectura (decidida por el usuario el 2026-11-13) ---
# Lista cerrada: consultas del sistema que no cambian nada, y lo que solo ordena o da formato
# a su salida. Nada que lea archivos (Get-Content, Select-String…): lo leído va al modelo, y
# un archivo puede traer instrucciones. Nada de ForEach-Object (`% Kill` llama a un método).
_READ_ONLY = frozenset({
    "get-date", "get-process", "gps", "ps", "get-service", "gsv", "get-netipaddress",
    "get-netipconfiguration", "gip", "get-netadapter", "get-dnsclientserveraddress",
    "get-nettcpconnection", "get-psdrive", "gdr", "get-volume", "get-disk", "get-physicaldisk",
    "get-computerinfo", "gin", "get-ciminstance", "gcim", "get-hotfix", "get-timezone",
    "get-culture", "get-uiculture", "get-host", "get-pnpdevice", "get-printer", "get-uptime",
    "get-location", "gl", "pwd",
    "select-object", "select", "where-object", "where", "?", "sort-object", "sort",
    "measure-object", "measure", "group-object", "group", "format-table", "ft", "format-list",
    "fl", "format-wide", "fw", "out-string", "convertto-json", "convertto-csv",
})  # fmt: skip
# Parámetros que leen de otro equipo o escriben en un archivo: entonces, rojo.
_NOT_READ_ONLY_PARAMS = frozenset(
    {"computername", "cimsession", "credential", "session", "outfile", "filepath", "path",
     "literalpath"}
)  # fmt: skip
# Métodos y tipos que solo calculan («[math]::Round(…)», «.ToString('N1')»).
_SAFE_MEMBERS = frozenset({"round", "floor", "ceiling", "abs", "min", "max", "tostring"})
_SAFE_TYPES = frozenset({
    "math", "system.math", "int", "int32", "int64", "long", "double", "decimal", "string",
    "datetime", "timespan",
})  # fmt: skip


def read_only(analysis: Analysis) -> bool:
    """True solo si todo lo que hay en el comando es de la lista cerrada de solo lectura.

    Se mira después de `blocked`; ante cualquier duda (una orden, un parámetro, un método o un
    tipo que no está en la lista, una asignación, una redirección), False: rojo, se confirma.
    """
    names = [re.split(r"[\\/]", raw.strip().lower())[-1] for raw in analysis.commands]
    return (
        bool(names)
        and not analysis.errors
        and not analysis.dynamic
        and not analysis.redirects
        and not analysis.assignments
        and all(n in _READ_ONLY for n in names)
        and not any(p.lower() in _NOT_READ_ONLY_PARAMS for p in analysis.params)
        and all(m.strip().lower() in _SAFE_MEMBERS for m in analysis.members)
        and all(t.strip().lower() in _SAFE_TYPES for t in analysis.types)
    )


def run_code(code: str, timeout_s: float = RUN_TIMEOUT_S) -> tuple[int, str]:
    """Ejecuta el código en PowerShell (sin perfil ni preguntas) y devuelve (código, salida)."""
    script = "[Console]::OutputEncoding = [Text.Encoding]::UTF8\n" + code
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    res = subprocess.run(
        [*_PS, "-EncodedCommand", encoded],
        capture_output=True,
        timeout=timeout_s,
        creationflags=_NO_WINDOW,
        check=False,
    )
    out = res.stdout.decode("utf-8", errors="replace").strip()
    err = res.stderr.decode("utf-8", errors="replace").strip()
    return res.returncode, out if res.returncode == 0 or not err else f"{out}\n{err}".strip()


def _clip(text: str) -> str:
    return text if len(text) <= MAX_OUTPUT else text[:MAX_OUTPUT].rstrip() + "\n…(recortado)"


class RunPowershellParams(Params):
    command: str = Field(
        min_length=1,
        max_length=2000,
        description="Comando de PowerShell exacto (solo si ninguna otra herramienta sirve)",
    )


class RunPowershell(Tool[RunPowershellParams]):
    name = "run_powershell"
    description = (
        "Ejecuta un comando de PowerShell; las consultas de solo lectura van sin preguntar y "
        "el resto, con confirmación. Solo si ninguna otra herramienta sirve. Ej.: «¿qué IP "
        "tengo?» (Get-NetIPAddress), «¿cuánto lleva encendido el PC?» ((Get-Date) - "
        "(Get-CimInstance Win32_OperatingSystem).LastBootUpTime)."
    )
    risk = Risk.RED
    green_when_read_only = True  # solo lo que pasa `read_only` (lista cerrada)
    game_policy = GamePolicy.BLOCKED
    category = Category.SYSTEM
    params_model = RunPowershellParams
    observe = True
    timeout_s = RUN_TIMEOUT_S + PARSE_TIMEOUT_S + 5

    def __init__(
        self,
        analyzer: Callable[[str], Analysis] = analyze,
        runner: Callable[[str], tuple[int, str]] = run_code,
    ) -> None:
        self._analyzer = analyzer
        self._runner = runner

    async def prepare(self, params: RunPowershellParams, ctx: ToolContext) -> Prepared:
        summary = "Ejecutar en PowerShell"
        try:
            analysis = await asyncio.to_thread(self._analyzer, params.command)
        except (OSError, subprocess.SubprocessError, ValueError):
            log.warning("No se pudo analizar el comando de PowerShell", exc_info=True)
            return Prepared(
                summary=summary,
                error=ToolResult.fail("No he podido revisar ese comando", "no lo ejecuto"),
            )
        if (reason := blocked(analysis)) is not None:
            log.info("run_powershell bloqueado (%s): %r", reason, params.command)
            return Prepared(
                summary=summary,
                error=ToolResult.fail("Ese comando no lo ejecuto", reason),
            )
        if read_only(analysis):
            # Solo consulta (lista cerrada): verde, sin preguntar. Se apunta en el registro.
            log.info("run_powershell de solo lectura: %r", params.command)
            return Prepared(summary=summary, detail=params.command, read_only=True)
        # Lo que se confirma es el comando exacto.
        return Prepared(summary=summary, detail=params.command, risk=Risk.RED)

    async def execute(
        self, params: RunPowershellParams, ctx: ToolContext, prepared: Prepared
    ) -> ToolResult:
        try:
            code, output = await asyncio.to_thread(self._runner, params.command)
        except subprocess.TimeoutExpired:
            return ToolResult.fail("PowerShell ha tardado demasiado", "lo he parado a los 20 s")
        except OSError:
            log.warning("No se pudo ejecutar PowerShell", exc_info=True)
            return ToolResult.fail("No he podido ejecutar PowerShell")
        output = _clip(output)
        if code != 0:
            return ToolResult(
                ok=False,
                message="El comando ha dado un error.",
                display="El comando ha dado un error",
                secondary=output.splitlines()[0][:80] if output else "",
                external=output or None,
                data={"exit_code": code},
            )
        return ToolResult(
            ok=True,
            message="He ejecutado el comando en PowerShell." if output else "Hecho, sin salida.",
            display="Comando ejecutado",
            secondary=output.splitlines()[0][:80] if output else "",
            external=output or None,
            data={"exit_code": code, "chars": len(output)},
        )
