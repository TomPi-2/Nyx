"""El informe de un día, tal como se envía (SPEC §8; 2026-11-16).

Un modelo estricto: solo caben los campos de la columna «se envía» de la SPEC. Lo que no está
aquí no puede salir del PC aunque alguien lo apunte por error en las cuentas del día. Es
también lo que enseña «ver qué se envía» en Ajustes → Privacidad.

- Versión de Nyx y de Windows; fabricante de la gráfica y VRAM y RAM por tramos; el modelo.
- Peticiones por camino (router, modelo…) y su latencia (mediana y p90), primer token.
- Uso de cada herramienta: solo su nombre y cuántas veces fue bien, mal o se canceló.
- Activaciones (confirmadas, falsas) y errores por código.
"""

from __future__ import annotations

import json
import platform
import re
import statistics
from datetime import date
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from nyx import __version__
from nyx.usage.stats import PATHS

Count = Annotated[int, Field(ge=0, le=1_000_000)]
Name = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,40}$")]
Code = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")]
_TOOL = re.compile(r"^[a-z][a-z0-9_]{0,40}$")


class Spread(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    p50: int = Field(ge=0)
    p90: int = Field(ge=0)
    n: Count


class ToolUse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: Count = 0
    fail: Count = 0
    cancelled: Count = 0


class Report(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    install_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    day: date
    app_version: str = Field(max_length=20)
    windows: str = Field(max_length=20)
    gpu_vendor: Literal["amd", "nvidia", "intel", "otra", "ninguna"]
    vram_gb: Literal["<6", "6-8", "8-12", "12-16", "16+", "?"]
    ram_gb: Literal["<16", "16-32", "32+", "?"]
    llm_model: str = Field(max_length=40)
    requests: dict[Literal["router", "llm", "shortcut", "refusal", "setup"], Count] = {}
    latency_ms: dict[Literal["router", "llm", "shortcut", "refusal", "setup"], Spread] = {}
    first_token_ms: Spread | None = None
    tools: dict[Name, ToolUse] = Field(default_factory=dict, max_length=120)
    activations: dict[Literal["ok", "false", "unverified"], Count] = {}
    errors: dict[Code, Count] = Field(default_factory=dict, max_length=60)


def spread(values: list[int]) -> Spread | None:
    if not values:
        return None
    ordered = sorted(values)
    p90 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.9))]
    return Spread(p50=round(statistics.median(ordered)), p90=p90, n=len(ordered))


def tool_use(actions_file: Path) -> dict[str, ToolUse]:
    """Cuántas veces se usó cada herramienta ese día (del registro de acciones): solo el
    nombre y el resultado; la frase y los parámetros se quedan en el PC."""
    counts: dict[str, dict[str, int]] = {}
    try:
        lines = actions_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    for line in lines:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        tool = str(record.get("tool", ""))
        if not _TOOL.match(tool):
            continue
        slot = counts.setdefault(tool, {"ok": 0, "fail": 0, "cancelled": 0})
        if record.get("decision") == "cancelled":
            slot["cancelled"] += 1
        elif record.get("ok") is True:
            slot["ok"] += 1
        elif record.get("ok") is False:
            slot["fail"] += 1
    return {k: ToolUse(**v) for k, v in sorted(counts.items())[:120]}


def band(value: float | None, edges: list[tuple[float, str]], top: str) -> str:
    if value is None:
        return "?"
    for limit, label in edges:
        if value < limit:
            return label
    return top


def hardware() -> dict[str, str]:
    """Fabricante de la gráfica y VRAM y RAM por tramos (nunca el modelo exacto)."""
    import psutil

    from nyx.setup.hardware import gpus

    found = gpus()
    name = found[0].name.lower() if found else ""
    vendor = next(
        (v for k, v in (("amd", "amd"), ("radeon", "amd"), ("nvidia", "nvidia"),
                        ("geforce", "nvidia"), ("intel", "intel")) if k in name),
        "otra" if found else "ninguna",
    )  # fmt: skip
    vram = found[0].vram_gb if found else None
    ram = psutil.virtual_memory().total / 1024**3
    return {
        "gpu_vendor": vendor,
        "vram_gb": band(vram, [(6, "<6"), (8.5, "6-8"), (12.5, "8-12"), (16.5, "12-16")], "16+"),
        "ram_gb": band(ram, [(15.5, "<16"), (32.5, "16-32")], "32+"),
    }


def build(
    install_id: str,
    day: date,
    counts: dict[str, Any],
    actions_file: Path,
    llm_model: str,
    hw: dict[str, str] | None = None,
) -> Report:
    latency = counts.get("latency_ms") or {}
    fields: dict[str, Any] = {
        "install_id": install_id,
        "day": day,
        "app_version": __version__[:20],
        "windows": platform.version()[:20],
        "llm_model": llm_model[:40],
        "requests": {k: v for k, v in (counts.get("requests") or {}).items() if k in PATHS},
        "latency_ms": {k: s for k in PATHS if (s := spread(list(latency.get(k) or [])))},
        "first_token_ms": spread(list(counts.get("first_token_ms") or [])),
        "tools": tool_use(actions_file),
        "activations": counts.get("activations") or {},
        "errors": counts.get("errors") or {},
        **(hw if hw is not None else hardware()),
    }
    # Validado como al enviarlo: lo que no encaje en el modelo no sale.
    return Report.model_validate(fields)
