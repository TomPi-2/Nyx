"""Medidor de recursos: CPU, RAM, gráfica y VRAM por proceso mientras se mide algo.

- CPU y RAM con psutil.
- Gráfica y VRAM por proceso con los contadores de rendimiento de Windows («GPU Engine» y
  «GPU Process Memory», los mismos del Administrador de tareas). Valen para AMD y NVIDIA.
  Se piden por su nombre en inglés (`PdhAddEnglishCounterW`), así funciona con Windows en
  cualquier idioma.

Muestrea en un hilo aparte (cada `interval_s`) para no molestar al bucle de asyncio.
"""

from __future__ import annotations

import ctypes
import re
import sys
import threading
import time
from collections import defaultdict
from collections.abc import Iterable
from ctypes import wintypes
from dataclasses import dataclass, field

import psutil

GPU_ENGINE = r"\GPU Engine(*)\Utilization Percentage"
GPU_PROC_MEM = r"\GPU Process Memory(*)\Dedicated Usage"

# Los procesos de Nyx que interesan (además del propio, si se pide).
NYX_PROCESSES = (
    "whisper-server.exe",
    "ollama.exe",
    "llama-server.exe",
    "ollama_llama_server.exe",
)

_PID = re.compile(r"pid_(\d+)_")
_ENGTYPE = re.compile(r"engtype_(.+)$")


# --- PDH (Windows) ---

PDH_FMT_DOUBLE = 0x00000200
PDH_MORE_DATA = 0x800007D2
ERROR_SUCCESS = 0


class _Value(ctypes.Union):
    _fields_ = [
        ("longValue", ctypes.c_long),
        ("doubleValue", ctypes.c_double),
        ("largeValue", ctypes.c_longlong),
        ("AnsiStringValue", ctypes.c_char_p),
        ("WideStringValue", ctypes.c_wchar_p),
    ]


class _FmtValue(ctypes.Structure):
    _fields_ = [("CStatus", wintypes.DWORD), ("value", _Value)]


class _Item(ctypes.Structure):
    _fields_ = [("szName", ctypes.c_wchar_p), ("FmtValue", _FmtValue)]


class _Pdh:
    """Una consulta PDH con contadores comodín (`(*)`): devuelve {instancia: valor}."""

    def __init__(self, paths: Iterable[str]) -> None:
        self._dll = ctypes.WinDLL("pdh.dll")  # type: ignore[attr-defined,unused-ignore]
        self._query = wintypes.HANDLE()
        self._check(self._dll.PdhOpenQueryW(None, None, ctypes.byref(self._query)), "abrir")
        self._counters: dict[str, wintypes.HANDLE] = {}
        for path in paths:
            handle = wintypes.HANDLE()
            status = self._dll.PdhAddEnglishCounterW(
                self._query, ctypes.c_wchar_p(path), None, ctypes.byref(handle)
            )
            if status == ERROR_SUCCESS:
                self._counters[path] = handle
        self._dll.PdhCollectQueryData(self._query)  # los porcentajes necesitan dos lecturas

    @staticmethod
    def _check(status: int, what: str) -> None:
        if status != ERROR_SUCCESS:
            raise OSError(f"PDH: no se pudo {what} (0x{status & 0xFFFFFFFF:08X})")

    @property
    def available(self) -> set[str]:
        return set(self._counters)

    def collect(self) -> dict[str, dict[str, float]]:
        self._dll.PdhCollectQueryData(self._query)
        out: dict[str, dict[str, float]] = {}
        for path, handle in self._counters.items():
            size = wintypes.DWORD(0)
            count = wintypes.DWORD(0)
            status = self._dll.PdhGetFormattedCounterArrayW(
                handle, PDH_FMT_DOUBLE, ctypes.byref(size), ctypes.byref(count), None
            )
            if (status & 0xFFFFFFFF) != PDH_MORE_DATA or size.value == 0:
                out[path] = {}
                continue
            buf = (ctypes.c_byte * size.value)()
            status = self._dll.PdhGetFormattedCounterArrayW(
                handle, PDH_FMT_DOUBLE, ctypes.byref(size), ctypes.byref(count), buf
            )
            if status != ERROR_SUCCESS:
                out[path] = {}
                continue
            items = ctypes.cast(buf, ctypes.POINTER(_Item))
            values: dict[str, float] = {}
            for i in range(count.value):
                item = items[i]
                if item.FmtValue.CStatus in (0, 1):  # válido (o válido y nuevo)
                    values[item.szName or ""] = item.FmtValue.value.doubleValue
            out[path] = values
        return out

    def close(self) -> None:
        self._dll.PdhCloseQuery(self._query)


# --- agregados ---


def gpu_by_pid(engines: dict[str, float]) -> tuple[dict[int, float], float]:
    """Uso de gráfica por proceso y total, como el Administrador de tareas: por cada tipo de
    motor (3D, Compute, Copy…) se suman sus instancias y se queda el tipo más alto."""
    per: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    total: dict[str, float] = defaultdict(float)
    for name, value in engines.items():
        pid = _PID.search(name)
        eng = _ENGTYPE.search(name)
        if pid is None or eng is None:
            continue
        per[int(pid.group(1))][eng.group(1)] += value
        total[eng.group(1)] += value
    by_pid = {pid: min(100.0, max(types.values())) for pid, types in per.items()}
    return by_pid, min(100.0, max(total.values(), default=0.0))


def vram_by_pid(memory: dict[str, float]) -> dict[int, float]:
    """VRAM dedicada por proceso, en MB."""
    out: dict[int, float] = defaultdict(float)
    for name, value in memory.items():
        if pid := _PID.search(name):
            out[int(pid.group(1))] += value / (1024 * 1024)
    return dict(out)


@dataclass
class ProcStat:
    cpu: list[float] = field(default_factory=list)  # % de un núcleo (como psutil)
    ram_mb: list[float] = field(default_factory=list)
    gpu: list[float] = field(default_factory=list)
    vram_mb: list[float] = field(default_factory=list)


def _stats(values: list[float]) -> tuple[float, float]:
    return (sum(values) / len(values), max(values)) if values else (0.0, 0.0)


class ResourceMonitor:
    """Muestrea los procesos que se llamen como `names` (y este, con `include_self`)."""

    def __init__(
        self,
        names: Iterable[str] = NYX_PROCESSES,
        *,
        include_self: bool = True,
        interval_s: float = 0.5,
    ) -> None:
        self.names = {n.lower() for n in names}
        self.include_self = include_self
        self.interval_s = interval_s
        self.procs: dict[str, ProcStat] = defaultdict(ProcStat)
        self.gpu_total: list[float] = []
        self.samples = 0
        self.gpu_ok = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._handles: dict[int, tuple[str, psutil.Process]] = {}

    def _find(self) -> None:
        me = psutil.Process()
        alive = {pid for pid in self._handles if psutil.pid_exists(pid)}
        self._handles = {pid: v for pid, v in self._handles.items() if pid in alive}
        for proc in psutil.process_iter(["name", "pid", "cmdline"]):
            name = (proc.info.get("name") or "").lower()
            if proc.pid in self._handles:
                continue
            cmdline = " ".join(proc.info.get("cmdline") or [])
            # El núcleo de Nyx abierto (instalado: «python -m nyx»; en desarrollo: «nyx»).
            nyx_core = name == "python.exe" and (" -m nyx" in cmdline or "\\nyx.exe" in cmdline)
            if name in self.names or nyx_core or (self.include_self and proc.pid == me.pid):
                if proc.pid == me.pid:
                    label = "este proceso"
                elif nyx_core:
                    label = f"núcleo de Nyx ({proc.pid})"
                else:
                    label = name
                try:
                    proc.cpu_percent(None)  # la primera lectura siempre da 0
                except psutil.Error:
                    continue
                self._handles[proc.pid] = (label, proc)

    def _loop(self) -> None:
        pdh: _Pdh | None = None
        if sys.platform == "win32":
            try:
                pdh = _Pdh([GPU_ENGINE, GPU_PROC_MEM])
                self.gpu_ok = GPU_ENGINE in pdh.available
            except OSError:
                pdh = None
        next_find = 0.0
        try:
            while not self._stop.wait(self.interval_s):
                now = time.monotonic()
                if now >= next_find:
                    self._find()
                    next_find = now + 3.0
                gpu: dict[int, float] = {}
                vram: dict[int, float] = {}
                if pdh is not None:
                    data = pdh.collect()
                    gpu, total = gpu_by_pid(data.get(GPU_ENGINE, {}))
                    vram = vram_by_pid(data.get(GPU_PROC_MEM, {}))
                    self.gpu_total.append(total)
                for pid, (label, proc) in list(self._handles.items()):
                    try:
                        cpu = proc.cpu_percent(None)
                        ram = proc.memory_info().rss / (1024 * 1024)
                    except psutil.Error:
                        self._handles.pop(pid, None)
                        continue
                    stat = self.procs[label]
                    stat.cpu.append(cpu)
                    stat.ram_mb.append(ram)
                    stat.gpu.append(gpu.get(pid, 0.0))
                    stat.vram_mb.append(vram.get(pid, 0.0))
                self.samples += 1
        finally:
            if pdh is not None:
                pdh.close()

    def start(self) -> ResourceMonitor:
        self._thread = threading.Thread(target=self._loop, name="resmon", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def __enter__(self) -> ResourceMonitor:
        return self.start()

    def __exit__(self, *_: object) -> None:
        self.stop()

    def report(self) -> str:
        """Tabla en Markdown: media y máximo de cada proceso."""
        cores = psutil.cpu_count() or 1
        lines = [
            f"Muestras: {self.samples} (cada {self.interval_s:g} s). CPU en % del equipo "
            f"({cores} hilos).",
            "",
            "| Proceso | CPU media / máx | RAM media / máx | Gráfica media / máx | VRAM máx |",
            "| --- | --- | --- | --- | --- |",
        ]
        for label, s in sorted(self.procs.items()):
            cpu_m, cpu_x = _stats(s.cpu)
            ram_m, ram_x = _stats(s.ram_mb)
            gpu_m, gpu_x = _stats(s.gpu)
            _, vram_x = _stats(s.vram_mb)
            lines.append(
                f"| {label} | {cpu_m / cores:.1f} % / {cpu_x / cores:.1f} % "
                f"| {ram_m:.0f} / {ram_x:.0f} MB "
                f"| {gpu_m:.1f} % / {gpu_x:.1f} % | {vram_x:.0f} MB |"
            )
        if self.gpu_total:
            m, x = _stats(self.gpu_total)
            lines += ["", f"Gráfica en total (todo el equipo): media {m:.1f} %, máx {x:.1f} %."]
        elif not self.gpu_ok:
            lines += ["", "Sin contadores de gráfica (no disponibles en este equipo)."]
        return "\n".join(lines) + "\n"
