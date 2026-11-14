"""system_info: estado del equipo con psutil (verde, observe, permitida en partida, 6.09).

Consulta batería (porcentaje y si está enchufado), uso de CPU, memoria RAM usada/total, espacio
libre por disco, el proceso que más CPU o RAM consume y la IP del equipo en la red local. Los
números van redondeados y en español natural para que el modelo los diga en una frase sin leer
rutas ni decimales largos.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import time
from typing import Any, Literal

import psutil
from pydantic import Field

from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult

log = logging.getLogger(__name__)

What = Literal["battery", "cpu", "ram", "disk", "top", "ip"]
CPU_SAMPLE_S = 0.2

_IGNORED_PROCESSES = frozenset(
    {"system idle process", "system", "idle", "registry", "memcompression"}
)


def _fmt_bytes(num_bytes: int | float) -> str:
    gb = num_bytes / (1024**3)
    if gb >= 1 or num_bytes <= 0:
        return f"{round(gb)} GB"
    mb = max(1, round(num_bytes / (1024**2)))
    return f"{mb} MB"


def _clean_proc_name(raw_name: str) -> str:
    name = raw_name.strip()
    if name.lower().endswith(".exe"):
        name = name[:-4]
    return name


def _battery(ps: Any) -> ToolResult:
    batt = ps.sensors_battery()
    if batt is None:
        return ToolResult(
            ok=True,
            message="Este equipo no tiene batería (está conectado a la corriente).",
            display="Sin batería",
            secondary="conectado a la corriente",
            data={"what": "battery", "has_battery": False},
        )
    pct = round(float(batt.percent))
    plugged = bool(batt.power_plugged)
    state = "enchufado" if plugged else "desenchufado"
    rem = ""
    mins_total = 0
    secs = getattr(batt, "secsleft", None)
    if not plugged and isinstance(secs, int | float) and 0 < secs < 24 * 3600:
        mins_total = round(float(secs) / 60)
        h, m = divmod(mins_total, 60)
        if h > 0 and m > 0:
            rem = f", quedan unas {h} h y {m} min"
        elif h > 0:
            rem = f", quedan unas {h} h"
        elif m > 0:
            rem = f", quedan unos {m} min"
    return ToolResult(
        ok=True,
        message=f"Tienes un {pct} % de batería y está {state}{rem}.",
        display=f"{pct} %",
        secondary=f"batería · {state}",
        data={
            "what": "battery",
            "has_battery": True,
            "percent": pct,
            "plugged": plugged,
            "remaining_min": mins_total,  # 0 si no se sabe o está enchufado
        },
    )


def _cpu(ps: Any, interval: float) -> ToolResult:
    pct = round(float(ps.cpu_percent(interval=interval)))
    return ToolResult(
        ok=True,
        message=f"El uso de CPU está al {pct} %.",
        display=f"CPU al {pct} %",
        secondary="uso del procesador",
        data={"what": "cpu", "percent": pct},
    )


def _ram(ps: Any) -> ToolResult:
    mem = ps.virtual_memory()
    used_gb = round(float(mem.used) / (1024**3))
    total_gb = round(float(mem.total) / (1024**3))
    pct = round(float(mem.percent))
    return ToolResult(
        ok=True,
        message=f"Estás usando {used_gb} GB de {total_gb} GB de RAM ({pct} %).",
        display=f"{used_gb} / {total_gb} GB",
        secondary=f"RAM en uso ({pct} %)",
        data={"what": "ram", "used_gb": used_gb, "total_gb": total_gb, "percent": pct},
    )


def _disk(ps: Any) -> ToolResult:
    disks: list[tuple[str, int, int]] = []
    for part in ps.disk_partitions(all=False):
        opts = str(getattr(part, "opts", "") or "").lower()
        fstype = str(getattr(part, "fstype", "") or "")
        if "cdrom" in opts or not fstype:
            continue
        try:
            usage = ps.disk_usage(part.mountpoint)
        except OSError:
            continue
        unit = str(getattr(part, "device", "") or part.mountpoint).rstrip("\\/")
        free_gb = round(float(usage.free) / (1024**3))
        total_gb = round(float(usage.total) / (1024**3))
        disks.append((unit, free_gb, total_gb))

    if not disks:
        return ToolResult.fail("No he podido leer el espacio de los discos")

    if len(disks) == 1:
        unit, free_gb, total_gb = disks[0]
        msg = f"Te quedan {free_gb} GB libres en {unit} (de {total_gb} GB)."
        display = f"{free_gb} GB libres"
        secondary = f"disco {unit} (de {total_gb} GB)"
    else:
        items = [f"{free} GB libres en {u} (de {tot} GB)" for u, free, tot in disks]
        msg = f"Te quedan {', '.join(items[:-1])} y {items[-1]}."
        u0, f0, _ = disks[0]
        display = f"{f0} GB libres en {u0}"
        secondary = " · ".join(f"{u}: {free} GB libres" for u, free, _ in disks)

    return ToolResult(
        ok=True,
        message=msg,
        display=display,
        secondary=secondary,
        data={
            "what": "disk",
            "disks": [{"unit": u, "free_gb": f, "total_gb": t} for u, f, t in disks],
        },
    )


def _top(ps: Any, interval: float) -> ToolResult:
    procs: list[tuple[Any, str]] = []
    for p in ps.process_iter(["pid", "name", "memory_info"]):
        try:
            info = p.info
            pid = int(info.get("pid") or 0)
            raw_name = str(info.get("name") or "").strip()
            if pid in (0, 4) or not raw_name or raw_name.lower() in _IGNORED_PROCESSES:
                continue
            p.cpu_percent(None)
            procs.append((p, _clean_proc_name(raw_name)))
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    if not procs:
        return ToolResult.fail("No he podido leer los procesos en ejecución")

    if interval > 0:
        time.sleep(interval)

    cpus = max(1, int(ps.cpu_count(logical=True) or 1))
    cpu_by_name: dict[str, float] = {}
    ram_by_name: dict[str, int] = {}
    for p, name in procs:
        try:
            cpu = float(p.cpu_percent(None) or 0.0) / cpus
            mem_info = p.info.get("memory_info") or p.memory_info()
            rss = int(getattr(mem_info, "rss", 0) or 0)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        cpu_by_name[name] = cpu_by_name.get(name, 0.0) + cpu
        ram_by_name[name] = ram_by_name.get(name, 0) + rss

    if not cpu_by_name and not ram_by_name:
        return ToolResult.fail("No he podido leer los procesos en ejecución")

    top_cpu = max(cpu_by_name, key=lambda n: (cpu_by_name[n], ram_by_name.get(n, 0)))
    top_ram = max(ram_by_name, key=lambda n: (ram_by_name[n], cpu_by_name.get(n, 0.0)))
    cpu_pct = min(100, max(0, round(cpu_by_name[top_cpu])))
    ram_bytes = ram_by_name[top_ram]
    ram_str = _fmt_bytes(ram_bytes)

    if top_cpu == top_ram:
        msg = (
            f"El proceso que más recursos usa es {top_cpu}: {cpu_pct} % de CPU y {ram_str} de RAM."
        )
        display = f"{top_cpu} ({cpu_pct} % CPU · {ram_str})"
        secondary = "proceso que más consume"
    else:
        msg = (
            f"El proceso que más CPU usa es {top_cpu} ({cpu_pct} %) y "
            f"el que más RAM usa es {top_ram} ({ram_str})."
        )
        display = f"CPU: {top_cpu} ({cpu_pct} %) · RAM: {top_ram} ({ram_str})"
        secondary = "procesos que más consumen"

    return ToolResult(
        ok=True,
        message=msg,
        display=display,
        secondary=secondary,
        data={
            "what": "top",
            "top_cpu": {"name": top_cpu, "percent": cpu_pct},
            "top_ram": {"name": top_ram, "bytes": ram_bytes, "formatted": ram_str},
        },
    )


# Dirección de documentación (RFC 5737): solo sirve para que Windows elija la conexión por la
# que saldría; con UDP, `connect` no manda nada.
_ROUTE_PROBE = ("192.0.2.1", 9)


def _ip() -> ToolResult:
    """La IP local de la conexión por la que sale el equipo (ERRORES.md, 2026-11-14: el modelo
    leía `Get-NetIPAddress` y se inventaba una). La pública no: habría que preguntar a una web."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(_ROUTE_PROBE)
            ip = str(sock.getsockname()[0])
    except OSError:
        ip = ""
    if not ip or ip.startswith(("0.", "127.", "169.254.")):
        return ToolResult.fail("No estás conectado a ninguna red", "sin IP")
    return ToolResult(
        ok=True,
        message=f"Tu IP en la red local es {ip}.",
        display=ip,
        secondary="IP local",
        data={"what": "ip", "ip": ip},
    )


class SystemInfoParams(Params):
    what: What = Field(
        description="Qué dato",
    )


class SystemInfo(Tool[SystemInfoParams]):
    name = "system_info"
    description = (
        "Consulta batería, CPU, RAM, disco libre, IP local o el proceso que más consume. "
        "Ej.: «¿cuánta RAM uso?» (what=ram), «¿qué consume más CPU?» (what=top)."
    )
    risk = Risk.GREEN
    game_policy = GamePolicy.ALLOWED
    category = Category.SYSTEM
    params_model = SystemInfoParams
    observe = True

    def __init__(self, *, ps: Any = None, cpu_interval: float = CPU_SAMPLE_S) -> None:
        self._ps = ps
        self._cpu_interval = cpu_interval

    def _query(self, what: What) -> ToolResult:
        ps = self._ps or psutil
        if what == "battery":
            return _battery(ps)
        if what == "cpu":
            return _cpu(ps, self._cpu_interval)
        if what == "ram":
            return _ram(ps)
        if what == "disk":
            return _disk(ps)
        if what == "ip":
            return _ip()
        return _top(ps, self._cpu_interval)

    async def run(self, params: SystemInfoParams, ctx: ToolContext) -> ToolResult:
        try:
            result = await asyncio.to_thread(self._query, params.what)
        except (OSError, psutil.Error) as exc:
            log.warning("system_info (%s) falló: %s", params.what, exc)
            return ToolResult.fail("No he podido consultar el estado del equipo")
        # Cada mensaje es ya una frase para decir («Te quedan 120 GB libres en C:»): 6.20a.
        return result.model_copy(update={"speak": True}) if result.ok else result
