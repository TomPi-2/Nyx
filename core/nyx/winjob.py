"""Job object de Windows: si el núcleo muere (incluso de golpe), sus procesos hijos mueren con él.

Sin esto, un whisper-server huérfano seguiría ocupando VRAM después de que Tauri reinicie
el núcleo. El núcleo se mete a sí mismo en un job con KILL_ON_JOB_CLOSE al arrancar, y
los procesos que lance después heredan el job.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes

log = logging.getLogger(__name__)

_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
# Permite que un proceso salga del job a propósito (Ollama: debe sobrevivir a Nyx).
_JOB_OBJECT_LIMIT_BREAKAWAY_OK = 0x0800

_job_handle: int | None = None  # se mantiene abierto mientras viva el proceso


class _BasicLimits(ctypes.Structure):
    _fields_ = (
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    )


class _IoCounters(ctypes.Structure):
    _fields_ = tuple((name, ctypes.c_uint64) for name in ("r", "w", "o", "rb", "wb", "ob"))


class _ExtendedLimits(ctypes.Structure):
    _fields_ = (
        ("BasicLimitInformation", _BasicLimits),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    )


def kill_children_on_exit() -> bool:
    """Mete el proceso actual en un job que mata a todos sus hijos al cerrarse."""
    global _job_handle
    if sys.platform != "win32" or _job_handle is not None:
        return _job_handle is not None
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        log.warning("No se pudo crear el job object (%d)", ctypes.get_last_error())
        return False
    info = _ExtendedLimits()
    info.BasicLimitInformation.LimitFlags = (
        _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | _JOB_OBJECT_LIMIT_BREAKAWAY_OK
    )
    ok = kernel32.SetInformationJobObject(
        wintypes.HANDLE(job),
        _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
        ctypes.byref(info),
        ctypes.sizeof(info),
    ) and kernel32.AssignProcessToJobObject(
        wintypes.HANDLE(job), wintypes.HANDLE(kernel32.GetCurrentProcess())
    )
    if not ok:
        log.warning("No se pudo configurar el job object (%d)", ctypes.get_last_error())
        kernel32.CloseHandle(wintypes.HANDLE(job))
        return False
    _job_handle = int(job)
    return True
