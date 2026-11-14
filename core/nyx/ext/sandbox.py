"""Lanzar una extensión con código encerrada (tarea 7.06; medido en la 7.05).

Lo que se aprobó con las medidas de `docs/benchmarks/aislamiento-7.05.md`:

- **AppContainer sin capacidades**, uno por extensión: Windows le impide leer los archivos del
  usuario, conectarse a nada (internet, la red de casa ni el propio PC), escribir en el
  registro, usar el portapapeles o lanzar otros programas.
- **Su propio escritorio**, vacío: desde el del usuario podría copiar la pantalla.
- **Un objeto de trabajo**: 1 proceso, tope de memoria, CPU con tope duro, prioridad baja (la
  mínima en partida), sin tocar nada de la interfaz, y muere si muere Nyx o el objeto.
- **Solo hereda tres asas** (entrada, salida y la nula para errores): nada más de Nyx.
- **Un entorno mínimo**: sin las variables de Nyx ni del usuario (claves, rutas).

Permisos de carpetas: el Python y el programa de dentro, lectura para cualquier contenedor
(runtime.py); su paquete, lectura solo para el suyo; su carpeta de datos, lectura y escritura
solo para el suyo. Lo demás (archivos del usuario, red) lo pide a Nyx (7.07).
"""

from __future__ import annotations

import contextlib
import ctypes
import hashlib
import logging
import msvcrt
import os
import subprocess
import sys
import threading
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

from nyx.ext import runtime

log = logging.getLogger(__name__)

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
adv = ctypes.WinDLL("advapi32", use_last_error=True)
uenv = ctypes.WinDLL("userenv", use_last_error=True)
u32 = ctypes.WinDLL("user32", use_last_error=True)

HANDLE = wintypes.HANDLE
DWORD = wintypes.DWORD

EXTENDED_STARTUPINFO_PRESENT = 0x80000
CREATE_SUSPENDED = 0x4
CREATE_NO_WINDOW = 0x08000000
CREATE_UNICODE_ENVIRONMENT = 0x400
STARTF_USESTDHANDLES = 0x100
PROC_THREAD_ATTRIBUTE_HANDLE_LIST = 0x20002
PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES = 0x20009
JOB_EXTENDED = 9
JOB_UI = 4
JOB_CPU_RATE = 15
LIMIT_ACTIVE_PROCESS = 0x8
LIMIT_PRIORITY_CLASS = 0x20
LIMIT_PROCESS_MEMORY = 0x100
LIMIT_DIE_ON_UNHANDLED_EXCEPTION = 0x400
LIMIT_KILL_ON_JOB_CLOSE = 0x2000
IDLE_PRIORITY_CLASS = 0x40
BELOW_NORMAL_PRIORITY_CLASS = 0x4000
UI_ALL = 0xFF
CPU_RATE_ENABLE = 0x1
CPU_RATE_HARD_CAP = 0x4
GENERIC_ALL_DESKTOP = 0x10000000
WAIT_TIMEOUT = 0x102
STILL_ACTIVE = 259
ALREADY_EXISTS = 0x800700B7


@dataclass(frozen=True, slots=True)
class Limits:
    """Lo que puede gastar. En partida, menos CPU y la prioridad mínima (cambia en caliente)."""

    memory_mb: int = 512
    cpu_percent: int = 10  # del total del equipo, con tope duro
    game_cpu_percent: int = 3


class STARTUPINFOW(ctypes.Structure):
    _fields_ = (
        ("cb", DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", DWORD),
        ("dwY", DWORD),
        ("dwXSize", DWORD),
        ("dwYSize", DWORD),
        ("dwXCountChars", DWORD),
        ("dwYCountChars", DWORD),
        ("dwFillAttribute", DWORD),
        ("dwFlags", DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.c_void_p),
        ("hStdInput", HANDLE),
        ("hStdOutput", HANDLE),
        ("hStdError", HANDLE),
    )


class STARTUPINFOEXW(ctypes.Structure):
    _fields_ = (("StartupInfo", STARTUPINFOW), ("lpAttributeList", ctypes.c_void_p))


class PROCESS_INFORMATION(ctypes.Structure):  # noqa: N801
    _fields_ = (
        ("hProcess", HANDLE),
        ("hThread", HANDLE),
        ("dwProcessId", DWORD),
        ("dwThreadId", DWORD),
    )


class SECURITY_CAPABILITIES(ctypes.Structure):  # noqa: N801
    _fields_ = (
        ("AppContainerSid", ctypes.c_void_p),
        ("Capabilities", ctypes.c_void_p),
        ("CapabilityCount", DWORD),
        ("Reserved", DWORD),
    )


class SECURITY_ATTRIBUTES(ctypes.Structure):  # noqa: N801
    _fields_ = (
        ("nLength", DWORD),
        ("lpSecurityDescriptor", ctypes.c_void_p),
        ("bInheritHandle", wintypes.BOOL),
    )


class BASIC_LIMITS(ctypes.Structure):  # noqa: N801
    _fields_ = (
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", DWORD),
        ("SchedulingClass", DWORD),
    )


class EXTENDED_LIMITS(ctypes.Structure):  # noqa: N801
    _fields_ = (
        ("Basic", BASIC_LIMITS),
        ("IoInfo", ctypes.c_uint64 * 6),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    )


k32.CreateJobObjectW.restype = HANDLE
u32.CreateDesktopW.restype = HANDLE


def _check(ok: Any, what: str) -> None:
    if not ok:
        error = ctypes.get_last_error()
        raise OSError(error, f"{what}: {ctypes.FormatError(error).strip()}")


# --- Nombres --------------------------------------------------------------------------------


def _short(ext_id: str) -> str:
    return hashlib.sha256(ext_id.encode("utf-8")).hexdigest()[:24]


def container_name(ext_id: str) -> str:
    """Nombre del AppContainer (máximo 64 caracteres; los id llegan a 81)."""
    return f"Tepnyx.Nyx.Ext.{_short(ext_id)}"


def desktop_name(ext_id: str) -> str:
    return f"NyxExt-{_short(ext_id)}"


# --- AppContainer -------------------------------------------------------------------------


def container_sid(ext_id: str) -> tuple[ctypes.c_void_p, str]:
    """Crea (o recupera) el AppContainer de la extensión. Devuelve el SID y su texto."""
    sid = ctypes.c_void_p()
    name = container_name(ext_id)
    hr = uenv.CreateAppContainerProfile(
        name, f"Nyx: {ext_id}"[:512], "Extensión de Nyx", None, 0, ctypes.byref(sid)
    )
    if hr & 0xFFFFFFFF == ALREADY_EXISTS:
        hr = uenv.DeriveAppContainerSidFromAppContainerName(name, ctypes.byref(sid))
    if hr != 0:
        raise OSError(f"AppContainer de {ext_id}: HRESULT {hr & 0xFFFFFFFF:#x}")
    text = wintypes.LPWSTR()
    _check(adv.ConvertSidToStringSidW(sid, ctypes.byref(text)), "ConvertSidToStringSid")
    value = text.value or ""
    k32.LocalFree(text)
    return sid, value


def delete_container(ext_id: str) -> None:
    """Al desinstalar: Windows borra la carpeta y el registro del contenedor (son suyos)."""
    uenv.DeleteAppContainerProfile(container_name(ext_id))


_user_sid: str | None = None


def user_sid() -> str:
    global _user_sid
    if _user_sid is None:
        token = HANDLE()
        k32.GetCurrentProcess.restype = HANDLE
        _check(
            adv.OpenProcessToken(HANDLE(k32.GetCurrentProcess()), 0x8, ctypes.byref(token)),
            "token",
        )
        size = DWORD()
        adv.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))  # TokenUser
        buf = ctypes.create_string_buffer(size.value)
        _check(adv.GetTokenInformation(token, 1, buf, size, ctypes.byref(size)), "TokenUser")
        k32.CloseHandle(token)
        text = wintypes.LPWSTR()
        sid = ctypes.c_void_p.from_buffer(buf).value
        _check(adv.ConvertSidToStringSidW(ctypes.c_void_p(sid), ctypes.byref(text)), "SID")
        _user_sid = text.value or ""
        k32.LocalFree(text)
    return _user_sid


def _desktop(ext_id: str, sid_text: str) -> int:
    """Un escritorio vacío para la extensión: el usuario, el sistema y su contenedor."""
    sd = ctypes.c_void_p()
    sddl = f"D:(A;;GA;;;{user_sid()})(A;;GA;;;SY)(A;;GA;;;{sid_text})"
    _check(
        adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(sd), None),
        "SDDL del escritorio",
    )
    sa = SECURITY_ATTRIBUTES(ctypes.sizeof(SECURITY_ATTRIBUTES), sd, False)
    desk = u32.CreateDesktopW(
        desktop_name(ext_id), None, None, 0, GENERIC_ALL_DESKTOP, ctypes.byref(sa)
    )
    k32.LocalFree(sd)
    _check(desk, "CreateDesktop")
    return int(desk)


# --- Objeto de trabajo ----------------------------------------------------------------------


def _job(limits: Limits) -> int:
    job = k32.CreateJobObjectW(None, None)
    _check(job, "CreateJobObject")
    info = EXTENDED_LIMITS()
    info.Basic.LimitFlags = (
        LIMIT_KILL_ON_JOB_CLOSE
        | LIMIT_DIE_ON_UNHANDLED_EXCEPTION
        | LIMIT_PROCESS_MEMORY
        | LIMIT_ACTIVE_PROCESS
        | LIMIT_PRIORITY_CLASS
    )
    info.ProcessMemoryLimit = limits.memory_mb * 2**20
    info.Basic.ActiveProcessLimit = 1
    info.Basic.PriorityClass = BELOW_NORMAL_PRIORITY_CLASS
    _check(
        k32.SetInformationJobObject(job, JOB_EXTENDED, ctypes.byref(info), ctypes.sizeof(info)),
        "límites del job",
    )
    ui = DWORD(UI_ALL)
    _check(k32.SetInformationJobObject(job, JOB_UI, ctypes.byref(ui), 4), "interfaz del job")
    _set_cpu(int(job), limits.cpu_percent)
    return int(job)


def _set_cpu(job: int, percent: int) -> None:
    rate = (DWORD * 2)(CPU_RATE_ENABLE | CPU_RATE_HARD_CAP, max(1, percent) * 100)
    _check(k32.SetInformationJobObject(HANDLE(job), JOB_CPU_RATE, rate, 8), "CPU del job")


def _set_priority(job: int, priority: int, memory_mb: int) -> None:
    info = EXTENDED_LIMITS()
    info.Basic.LimitFlags = (
        LIMIT_KILL_ON_JOB_CLOSE
        | LIMIT_DIE_ON_UNHANDLED_EXCEPTION
        | LIMIT_PROCESS_MEMORY
        | LIMIT_ACTIVE_PROCESS
        | LIMIT_PRIORITY_CLASS
    )
    info.ProcessMemoryLimit = memory_mb * 2**20
    info.Basic.ActiveProcessLimit = 1
    info.Basic.PriorityClass = priority
    _check(
        k32.SetInformationJobObject(
            HANDLE(job), JOB_EXTENDED, ctypes.byref(info), ctypes.sizeof(info)
        ),
        "prioridad del job",
    )


# --- El proceso -----------------------------------------------------------------------------


class SandboxProcess:
    """Una extensión en marcha. `stdin`/`stdout` son los extremos de Nyx de sus tuberías."""

    def __init__(
        self,
        pid: int,
        process: int,
        job: int,
        desktop: int,
        stdin: IO[bytes],
        stdout: IO[bytes],
        limits: Limits,
    ) -> None:
        self.pid = pid
        self.stdin = stdin
        self.stdout = stdout
        self._process = process
        self._job = job
        self._desktop = desktop
        self._limits = limits
        self._lock = threading.Lock()
        self._closed = False

    def poll(self) -> int | None:
        """El código de salida, o None si sigue en marcha."""
        with self._lock:
            if self._closed:
                return -1
            code = DWORD()
            k32.GetExitCodeProcess(HANDLE(self._process), ctypes.byref(code))
            return None if code.value == STILL_ACTIVE else int(code.value)

    def wait(self, timeout: float) -> int | None:
        with self._lock:
            if self._closed:
                return -1
            k32.WaitForSingleObject(HANDLE(self._process), int(timeout * 1000))
        return self.poll()

    def set_game(self, active: bool) -> None:
        """En partida: CPU al mínimo y prioridad «inactiva»; al salir, como antes."""
        with self._lock:
            if self._closed:
                return
            percent = self._limits.game_cpu_percent if active else self._limits.cpu_percent
            priority = IDLE_PRIORITY_CLASS if active else BELOW_NORMAL_PRIORITY_CLASS
            _set_cpu(self._job, percent)
            _set_priority(self._job, priority, self._limits.memory_mb)

    def kill(self) -> None:
        """Mata el proceso (cerrar el job lo mata: KILL_ON_JOB_CLOSE) y suelta todo."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            k32.TerminateJobObject(HANDLE(self._job), 1)
            k32.CloseHandle(HANDLE(self._job))
            k32.CloseHandle(HANDLE(self._process))
            u32.CloseDesktop(HANDLE(self._desktop))
        for pipe in (self.stdin, self.stdout):
            with contextlib.suppress(OSError):
                pipe.close()


class SandboxLauncher:
    """Lanza extensiones encerradas. Una instancia para todo Nyx."""

    def __init__(
        self,
        limits: Limits | None = None,
        *,
        runtime_root: Path | None = None,
        data_root: Path | None = None,
    ) -> None:
        self.limits = limits or Limits()
        self._runtime_root = runtime_root
        self._data_root = data_root
        self._granted: set[tuple[str, str]] = set()
        self.game = False

    def start(self, ext_id: str, package: Path) -> SandboxProcess:
        """Lanza la extensión. Bloquea (descarga el Python si falta): desde asyncio, en un hilo."""
        if sys.platform != "win32":
            raise OSError("las extensiones con código solo funcionan en Windows")
        python = runtime.ensure_python(self._runtime_root)
        runner = runtime.ensure_runner(self._runtime_root)
        data = runtime.data_dir(ext_id, self._data_root)
        (data / "tmp").mkdir(parents=True, exist_ok=True)
        sid, sid_text = container_sid(ext_id)
        for path, rights in ((package, "RX"), (data, "M")):
            if (str(path), sid_text) not in self._granted:
                runtime.grant(path, f"*{sid_text}", rights)
                self._granted.add((str(path), sid_text))
        desktop = _desktop(ext_id, sid_text)
        try:
            argv = [
                str(python / "python.exe"),
                "-I",
                "-X",
                "utf8",
                str(runner),
                str(package),
                str(data),
            ]
            env = {
                "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"),
                "WINDIR": os.environ.get("WINDIR", r"C:\Windows"),
                # CreateProcess las cambia por las del contenedor; sin ellas falla (error 203).
                "LOCALAPPDATA": os.environ.get("LOCALAPPDATA", ""),
                "USERPROFILE": os.environ.get("USERPROFILE", ""),
                "TEMP": str(data / "tmp"),
                "TMP": str(data / "tmp"),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUTF8": "1",
            }
            return self._spawn(argv, data, env, sid, desktop, ext_id)
        except BaseException:
            u32.CloseDesktop(HANDLE(desktop))
            raise

    def _spawn(
        self,
        argv: list[str],
        cwd: Path,
        env: dict[str, str],
        sid: ctypes.c_void_p,
        desktop: int,
        ext_id: str,
    ) -> SandboxProcess:
        # Tuberías: Nyx escribe en la entrada de la extensión y lee su salida.
        in_read, in_write = os.pipe()
        out_read, out_write = os.pipe()
        null = os.open(os.devnull, os.O_RDWR)
        child = [msvcrt.get_osfhandle(fd) for fd in (in_read, out_write, null)]
        for handle in child:
            os.set_handle_inheritable(handle, True)

        si = STARTUPINFOEXW()
        si.StartupInfo.cb = ctypes.sizeof(si)
        si.StartupInfo.dwFlags = STARTF_USESTDHANDLES
        si.StartupInfo.lpDesktop = f"WinSta0\\{desktop_name(ext_id)}"
        si.StartupInfo.hStdInput = child[0]
        si.StartupInfo.hStdOutput = child[1]
        si.StartupInfo.hStdError = child[2]
        handles = (HANDLE * 3)(*child)
        size = ctypes.c_size_t()
        k32.InitializeProcThreadAttributeList(None, 2, 0, ctypes.byref(size))
        attrs = ctypes.create_string_buffer(size.value)
        _check(k32.InitializeProcThreadAttributeList(attrs, 2, 0, ctypes.byref(size)), "atributos")
        caps = SECURITY_CAPABILITIES()
        caps.AppContainerSid = sid  # sin capacidades: ni red ni nada
        process = PROCESS_INFORMATION()
        try:
            _check(
                k32.UpdateProcThreadAttribute(
                    attrs,
                    0,
                    PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
                    handles,
                    ctypes.sizeof(handles),
                    None,
                    None,
                ),
                "lista de asas",
            )
            _check(
                k32.UpdateProcThreadAttribute(
                    attrs,
                    0,
                    PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
                    ctypes.byref(caps),
                    ctypes.sizeof(caps),
                    None,
                    None,
                ),
                "AppContainer",
            )
            si.lpAttributeList = ctypes.cast(attrs, ctypes.c_void_p)
            block = "".join(f"{k}={v}\0" for k, v in sorted(env.items())) + "\0"
            flags = (
                EXTENDED_STARTUPINFO_PRESENT
                | CREATE_SUSPENDED
                | CREATE_NO_WINDOW
                | CREATE_UNICODE_ENVIRONMENT
            )
            ok = k32.CreateProcessW(
                None,
                ctypes.create_unicode_buffer(subprocess.list2cmdline(argv)),
                None,
                None,
                True,
                flags,
                ctypes.create_unicode_buffer(block, len(block)),
                str(cwd),
                ctypes.byref(si),
                ctypes.byref(process),
            )
            error = ctypes.get_last_error()
        finally:
            k32.DeleteProcThreadAttributeList(attrs)
            for fd in (in_read, out_write, null):  # los extremos de la extensión ya son suyos
                os.close(fd)
        if not ok:
            os.close(in_write)
            os.close(out_read)
            raise OSError(error, f"no se pudo lanzar la extensión: {ctypes.FormatError(error)}")
        # Antes de que corra una sola instrucción: dentro del job y con sus límites.
        try:
            job = _job(self.limits)
            _check(k32.AssignProcessToJobObject(HANDLE(job), process.hProcess), "meter en el job")
        except OSError:
            k32.TerminateProcess(process.hProcess, 1)
            k32.CloseHandle(process.hProcess)
            k32.CloseHandle(process.hThread)
            os.close(in_write)
            os.close(out_read)
            raise
        proc = SandboxProcess(
            int(process.dwProcessId),
            int(process.hProcess),
            job,
            desktop,
            os.fdopen(in_write, "wb", buffering=0),
            os.fdopen(out_read, "rb"),
            self.limits,
        )
        if self.game:
            proc.set_game(True)
        k32.ResumeThread(process.hThread)
        k32.CloseHandle(process.hThread)
        log.info("Extensión %s en marcha (pid %s, encerrada)", ext_id, proc.pid)
        return proc
