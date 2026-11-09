"""Datos del equipo para los informes de rendimiento (requisitos mínimos)."""

from __future__ import annotations

import json
import platform
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

REPORTS_DIR = Path(__file__).resolve().parents[2] / "docs" / "benchmarks"

_PS = (
    "$g = Get-CimInstance Win32_VideoController | Select-Object Name, DriverVersion;"
    "$c = (Get-CimInstance Win32_Processor | Select-Object -First 1).Name;"
    "$r = (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory;"
    "$o = (Get-CimInstance Win32_OperatingSystem) | Select-Object Caption, BuildNumber;"
    "@{gpus=@($g); cpu=$c; ram=$r; os=$o} | ConvertTo-Json -Depth 3 -Compress"
)


def hardware() -> dict[str, Any]:
    info: dict[str, Any] = {"machine": platform.node(), "python": platform.python_version()}
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", _PS],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        ).stdout
        data = json.loads(out)
        info["cpu"] = (data.get("cpu") or "").strip()
        info["ram_gb"] = round(int(data.get("ram") or 0) / 2**30, 1)
        info["gpus"] = [f"{g['Name']} ({g['DriverVersion']})" for g in data.get("gpus", [])]
        os_info = data.get("os") or {}
        info["os"] = f"{os_info.get('Caption', '')} build {os_info.get('BuildNumber', '')}".strip()
    except (OSError, subprocess.SubprocessError, ValueError, KeyError) as exc:
        info["error"] = f"no se pudo leer el hardware: {exc}"
    return info


def save_report(kind: str, report: dict[str, Any]) -> Path:
    """Guarda el informe en docs/benchmarks/<tipo>-<equipo>-<fecha>.json."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    machine = re.sub(r"[^A-Za-z0-9_-]", "_", platform.node()) or "pc"
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    path = REPORTS_DIR / f"{kind}-{machine}-{stamp}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
