"""Sonda de aislamiento para las extensiones con código (tarea 7.05).

Lanza el Python «embeddable» oficial de tres formas —sin aislar, con un token de baja
integridad y dentro de un AppContainer sin capacidades—, siempre en un objeto de trabajo con
límites, y en cada una prueba lo que una extensión mala intentaría: leer y escribir archivos
del usuario, abrir la red (internet y el propio PC), tocar el registro, lanzar procesos, leer
el portapapeles o la pantalla y pasarse de memoria o de CPU. Nada destructivo: escribe solo en
la carpeta de trabajo y en una clave de registro propia que borra al acabar; no lee el
contenido del portapapeles ni de tus Documentos (solo si se puede).

    uv run python scripts/sandbox_probe.py --python <carpeta del embeddable> --trabajo <carpeta>
        [--informe docs/benchmarks/aislamiento-7.05.md]
"""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import json
import os
import platform
import socket
import statistics
import subprocess
import sys
import threading
import time
import winreg
from ctypes import wintypes
from pathlib import Path
from typing import Any

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
adv = ctypes.WinDLL("advapi32", use_last_error=True)
uenv = ctypes.WinDLL("userenv", use_last_error=True)

HANDLE = wintypes.HANDLE
DWORD = wintypes.DWORD

EXTENDED_STARTUPINFO_PRESENT = 0x80000
CREATE_SUSPENDED = 0x4
CREATE_NO_WINDOW = 0x08000000
CREATE_UNICODE_ENVIRONMENT = 0x400
STARTF_USESTDHANDLES = 0x100
PROC_THREAD_ATTRIBUTE_HANDLE_LIST = 0x20002
PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES = 0x20009
# AppContainer «menos privilegiado» (LPAC): sin lo que Windows da a todas las apps.
PROC_THREAD_ATTRIBUTE_ALL_APPLICATION_PACKAGES_POLICY = 0x2000F

# Límites del objeto de trabajo (como haría el host de la 7.06).
JOB_EXTENDED = 9
JOB_UI = 4
JOB_CPU_RATE = 15
LIMIT_ACTIVE_PROCESS = 0x8
LIMIT_PRIORITY_CLASS = 0x20
LIMIT_PROCESS_MEMORY = 0x100
LIMIT_DIE_ON_UNHANDLED_EXCEPTION = 0x400
LIMIT_KILL_ON_JOB_CLOSE = 0x2000
BELOW_NORMAL_PRIORITY_CLASS = 0x4000
UI_ALL = 0xFF  # handles, portapapeles, parámetros del sistema, pantalla, átomos, escritorio, salir
CPU_RATE_ENABLE = 0x1
CPU_RATE_HARD_CAP = 0x4

MEMORY_LIMIT = 256 * 1024 * 1024
CPU_RATE_PERCENT = 3  # del total del equipo


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


def user_sid() -> str:
    out = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, text=True)
    return out.stdout.strip().split(",")[-1].strip('"')


class SID_AND_ATTRIBUTES(ctypes.Structure):  # noqa: N801
    _fields_ = (("Sid", ctypes.c_void_p), ("Attributes", DWORD))


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


def _check(ok: Any, what: str) -> None:
    if not ok:
        raise OSError(
            ctypes.get_last_error(), f"{what}: {ctypes.FormatError(ctypes.get_last_error())}"
        )


# --- AppContainer -------------------------------------------------------------------------

CONTAINER = "Tepnyx.Nyx.SondaExtensiones"
DESKTOP = "NyxSondaExtensiones"
MODES = ("normal", "baja", "appcontainer", "appcontainer_escritorio", "lpac_escritorio")


def appcontainer_sid() -> tuple[ctypes.c_void_p, str]:
    sid = ctypes.c_void_p()
    hr = uenv.CreateAppContainerProfile(
        CONTAINER, "Nyx: sonda de extensiones", "Prueba de aislamiento (7.05)", None, 0,
        ctypes.byref(sid),
    )  # fmt: skip
    if hr & 0xFFFFFFFF == 0x800700B7:  # ya existe
        hr = uenv.DeriveAppContainerSidFromAppContainerName(CONTAINER, ctypes.byref(sid))
    if hr != 0:
        raise OSError(f"AppContainer: HRESULT {hr & 0xFFFFFFFF:#x}")
    text = wintypes.LPWSTR()
    _check(adv.ConvertSidToStringSidW(sid, ctypes.byref(text)), "ConvertSidToStringSid")
    return sid, text.value or ""


def delete_appcontainer() -> None:
    uenv.DeleteAppContainerProfile(CONTAINER)


# --- Token de baja integridad -------------------------------------------------------------


def low_integrity_token() -> HANDLE:
    TOKEN_ALL = 0xF01FF  # noqa: N806
    token = HANDLE()
    k32.GetCurrentProcess.restype = HANDLE
    _check(
        adv.OpenProcessToken(HANDLE(k32.GetCurrentProcess()), TOKEN_ALL, ctypes.byref(token)),
        "token",
    )
    dup = HANDLE()
    _check(adv.DuplicateTokenEx(token, TOKEN_ALL, None, 2, 1, ctypes.byref(dup)), "duplicar")
    sid = ctypes.c_void_p()
    _check(adv.ConvertStringSidToSidW("S-1-16-4096", ctypes.byref(sid)), "SID baja")
    label = SID_AND_ATTRIBUTES(sid, 0x20)  # SE_GROUP_INTEGRITY
    _check(
        adv.SetTokenInformation(
            dup, 25, ctypes.byref(label), ctypes.sizeof(label) + adv.GetLengthSid(sid)
        ),
        "nivel de integridad",
    )
    return dup


# --- Lanzar en un job ----------------------------------------------------------------------


def make_job(limits: bool) -> HANDLE:
    k32.CreateJobObjectW.restype = HANDLE
    job = k32.CreateJobObjectW(None, None)
    info = EXTENDED_LIMITS()
    info.Basic.LimitFlags = LIMIT_KILL_ON_JOB_CLOSE | LIMIT_DIE_ON_UNHANDLED_EXCEPTION
    if limits:
        info.Basic.LimitFlags |= LIMIT_PROCESS_MEMORY | LIMIT_ACTIVE_PROCESS | LIMIT_PRIORITY_CLASS
        info.ProcessMemoryLimit = MEMORY_LIMIT
        info.Basic.ActiveProcessLimit = 1
        info.Basic.PriorityClass = BELOW_NORMAL_PRIORITY_CLASS
    _check(
        k32.SetInformationJobObject(job, JOB_EXTENDED, ctypes.byref(info), ctypes.sizeof(info)),
        "job",
    )
    if limits:
        ui = DWORD(UI_ALL)
        _check(k32.SetInformationJobObject(job, JOB_UI, ctypes.byref(ui), 4), "job UI")
        rate = (DWORD * 2)(CPU_RATE_ENABLE | CPU_RATE_HARD_CAP, CPU_RATE_PERCENT * 100)
        _check(k32.SetInformationJobObject(job, JOB_CPU_RATE, rate, 8), "job CPU")
    return HANDLE(job)


def launch(
    mode: str, argv: list[str], cwd: Path, env: dict[str, str], limits: bool,
    container_sid: ctypes.c_void_p | None, desktop: str | None = None, lpac: bool = False,
) -> tuple[int, list[str], float | None, int, float]:  # fmt: skip
    """Devuelve (código de salida, líneas de stdout, s hasta la 1.ª línea, pico de memoria, s)."""
    read_fd, write_fd = os.pipe()
    import msvcrt

    write_h = msvcrt.get_osfhandle(write_fd)
    os.set_handle_inheritable(write_h, True)
    null = open(os.devnull, "rb")  # noqa: SIM115
    null_h = msvcrt.get_osfhandle(null.fileno())
    os.set_handle_inheritable(null_h, True)

    si = STARTUPINFOEXW()
    si.StartupInfo.cb = ctypes.sizeof(si)
    si.StartupInfo.dwFlags = STARTF_USESTDHANDLES
    if desktop:
        si.StartupInfo.lpDesktop = f"WinSta0\\{desktop}"
    si.StartupInfo.hStdInput = null_h
    si.StartupInfo.hStdOutput = write_h
    si.StartupInfo.hStdError = write_h

    # Solo se heredan las dos asas de la lista: nada más del proceso de Nyx.
    handles = (HANDLE * 2)(null_h, write_h)
    size = ctypes.c_size_t()
    k32.InitializeProcThreadAttributeList(None, 3, 0, ctypes.byref(size))
    attrs = ctypes.create_string_buffer(size.value)
    _check(k32.InitializeProcThreadAttributeList(attrs, 3, 0, ctypes.byref(size)), "atributos")
    _check(
        k32.UpdateProcThreadAttribute(
            attrs, 0, PROC_THREAD_ATTRIBUTE_HANDLE_LIST, handles, ctypes.sizeof(handles), None, None
        ),
        "lista de asas",
    )
    caps = SECURITY_CAPABILITIES()
    if container_sid is not None:
        caps.AppContainerSid = container_sid  # sin capacidades: ni red ni nada
        _check(
            k32.UpdateProcThreadAttribute(
                attrs, 0, PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES, ctypes.byref(caps),
                ctypes.sizeof(caps), None, None,
            ),
            "AppContainer",
        )  # fmt: skip
    opt_out = DWORD(1)
    if lpac:
        _check(
            k32.UpdateProcThreadAttribute(
                attrs, 0, PROC_THREAD_ATTRIBUTE_ALL_APPLICATION_PACKAGES_POLICY,
                ctypes.byref(opt_out), ctypes.sizeof(opt_out), None, None,
            ),
            "LPAC",
        )  # fmt: skip
    si.lpAttributeList = ctypes.cast(attrs, ctypes.c_void_p)

    cmdline = subprocess.list2cmdline(argv)
    env_block = "".join(f"{k}={v}\0" for k, v in sorted(env.items())) + "\0"
    flags = (
        EXTENDED_STARTUPINFO_PRESENT | CREATE_SUSPENDED | CREATE_NO_WINDOW
        | CREATE_UNICODE_ENVIRONMENT
    )  # fmt: skip
    pi = PROCESS_INFORMATION()
    buf = ctypes.create_unicode_buffer(cmdline)
    env_buf = ctypes.create_unicode_buffer(env_block, len(env_block))
    if mode == "baja":
        token = low_integrity_token()
        ok = adv.CreateProcessAsUserW(
            token, None, buf, None, None, True, flags, env_buf, str(cwd), ctypes.byref(si),
            ctypes.byref(pi),
        )  # fmt: skip
        k32.CloseHandle(token)
    else:
        ok = k32.CreateProcessW(
            None, buf, None, None, True, flags, env_buf, str(cwd), ctypes.byref(si),
            ctypes.byref(pi),
        )  # fmt: skip
    error = ctypes.get_last_error()
    k32.DeleteProcThreadAttributeList(attrs)
    os.close(write_fd)
    null.close()
    if not ok:
        raise OSError(error, f"CreateProcess ({mode}): {ctypes.FormatError(error)}")

    job = make_job(limits)
    _check(k32.AssignProcessToJobObject(job, pi.hProcess), "meter en el job")
    lines: list[str] = []
    first: list[float] = []
    start = time.perf_counter()

    def reader() -> None:
        with os.fdopen(read_fd, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if not first:
                    first.append(time.perf_counter() - start)
                lines.append(line.rstrip("\n"))

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    k32.ResumeThread(pi.hThread)
    k32.WaitForSingleObject(pi.hProcess, 60_000)
    elapsed = time.perf_counter() - start
    t.join(5)
    code = DWORD()
    k32.GetExitCodeProcess(pi.hProcess, ctypes.byref(code))
    info = EXTENDED_LIMITS()
    k32.QueryInformationJobObject(job, JOB_EXTENDED, ctypes.byref(info), ctypes.sizeof(info), None)
    for h in (pi.hThread, pi.hProcess, job):
        k32.CloseHandle(h)
    return code.value, lines, (first[0] if first else None), info.PeakProcessMemoryUsed, elapsed


# --- Lo que hace la «extensión» -------------------------------------------------------------

PAYLOAD = r"""
import json, os, socket, sys, time
print("ready", flush=True)
cfg = json.loads(sys.argv[1])
out = {}

def probe(name, fn):
    try:
        r = fn()
        out[name] = ["permitido", str(r)[:80]]
    except BaseException as e:  # noqa
        out[name] = ["bloqueado", f"{type(e).__name__}: {e}"[:120]]

def read_secret():
    with open(cfg["secret"], encoding="utf-8") as f:
        return len(f.read())

def write_outside():
    with open(cfg["outside"], "w") as f:
        f.write("x")
    return "escrito"

def write_own():
    with open(os.path.join(cfg["own"], "datos.txt"), "w") as f:
        f.write("x")
    return "escrito"

def connect(host, port):
    s = socket.create_connection((host, port), timeout=3)
    s.close()
    return "conectado"

def reg_read():
    import winreg
    k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer")
    winreg.CloseKey(k)
    return "abierta"

def reg_recent():
    import winreg
    k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\RecentDocs")
    n = winreg.QueryInfoKey(k)[1]
    winreg.CloseKey(k)
    return f"{n} valores (no se leen)"

def reg_write():
    import winreg
    k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\NyxSondaExtensiones")
    winreg.CloseKey(k)
    return "creada"

def spawn():
    import subprocess
    return subprocess.run(["cmd", "/c", "echo hola"], capture_output=True, timeout=5).returncode

def user32():
    import ctypes
    return ctypes.WinDLL("user32", use_last_error=True)

def clipboard():
    u = user32()
    if not u.OpenClipboard(None):
        import ctypes
        raise OSError(ctypes.get_last_error(), "OpenClipboard")
    u.CloseClipboard()
    return "abierto (sin leerlo)"

def screen():
    import ctypes
    u, g = user32(), ctypes.WinDLL("gdi32")
    u.GetDC.restype = ctypes.c_void_p
    g.CreateCompatibleDC.restype = ctypes.c_void_p
    g.CreateCompatibleBitmap.restype = ctypes.c_void_p
    w, h = u.GetSystemMetrics(0), u.GetSystemMetrics(1)
    src = u.GetDC(None)
    if not src:
        raise OSError("GetDC")
    dst = g.CreateCompatibleDC(ctypes.c_void_p(src))
    bmp = g.CreateCompatibleBitmap(ctypes.c_void_p(src), 32, 32)
    g.SelectObject(ctypes.c_void_p(dst), ctypes.c_void_p(bmp))
    # Toda la pantalla reducida a 32x32: si salen colores distintos, se ha visto de verdad.
    ok = g.StretchBlt(ctypes.c_void_p(dst), 0, 0, 32, 32, ctypes.c_void_p(src), 0, 0, w, h, 0x00CC0020)
    colors = {g.GetPixel(ctypes.c_void_p(dst), x, y) for x in range(0, 32, 2) for y in range(0, 32, 2)}
    g.DeleteObject(ctypes.c_void_p(bmp)); g.DeleteDC(ctypes.c_void_p(dst))
    u.ReleaseDC(None, ctypes.c_void_p(src))
    if not ok:
        raise OSError("StretchBlt")
    if len(colors) <= 1:
        raise OSError(f"imagen vacía ({w}x{h}, un solo color)")
    return f"{w}x{h}, {len(colors)} colores distintos"

def foreground_title():
    u = user32()
    import ctypes
    u.GetForegroundWindow.restype = ctypes.c_void_p
    buf = ctypes.create_unicode_buffer(256)
    n = u.GetWindowTextW(ctypes.c_void_p(u.GetForegroundWindow()), buf, 256)
    if not n:
        raise OSError(ctypes.get_last_error(), "sin título")
    return f"{n} letras (no se guardan)"

def memory():
    b = bytearray(512 * 1024 * 1024)
    return len(b)

def cpu():
    t0, c0 = time.perf_counter(), time.process_time()
    while time.perf_counter() - t0 < 2.0:
        pass
    return round((time.process_time() - c0) / (time.perf_counter() - t0), 3)

probe("modulos", lambda: [__import__(m).__name__ for m in ("ssl", "sqlite3", "ctypes", "asyncio")])
probe("leer_archivo_usuario", read_secret)
probe("listar_documentos", lambda: len(os.listdir(cfg["documents"])))
probe("escribir_fuera", write_outside)
probe("escribir_su_carpeta", write_own)
probe("red_internet", lambda: connect("1.1.1.1", 443))
probe("dns", lambda: socket.getaddrinfo("example.com", 443)[0][4][0])
probe("red_este_pc", lambda: connect("127.0.0.1", cfg["port"]))
probe("registro_leer", reg_read)
probe("registro_recientes", reg_recent)
probe("registro_escribir", reg_write)
probe("lanzar_proceso", spawn)
probe("portapapeles", clipboard)
probe("pantalla", screen)
probe("titulo_ventana_activa", foreground_title)
probe("variables_de_entorno", lambda: sorted(os.environ))
probe("memoria_512MB", memory)
probe("cpu_un_hilo_2s", cpu)
print(json.dumps(out, ensure_ascii=False), flush=True)
"""


def icacls(*args: str) -> None:
    subprocess.run(["icacls", *args], check=True, capture_output=True)


def run(python_dir: Path, work: Path, report: Path | None) -> None:
    python = python_dir / "python.exe"
    user = work / "usuario"  # hace de carpeta del usuario: no se le da permiso a nadie
    own = work / "extension"  # la carpeta propia de la extensión
    for d in (user, own):
        d.mkdir(parents=True, exist_ok=True)
    (user / "secreto.txt").write_text("contenido privado", encoding="utf-8")
    (own / "sonda.py").write_text(PAYLOAD, encoding="utf-8")
    (own / "tmp").mkdir(exist_ok=True)

    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    port = server.getsockname()[1]

    def accept() -> None:
        while True:
            try:
                conn, _ = server.accept()
                conn.close()
            except OSError:
                return

    threading.Thread(target=accept, daemon=True).start()

    sid, sid_text = appcontainer_sid()
    # Un escritorio aparte, sin ventanas del usuario (como el de Chromium para sus procesos).
    u32 = ctypes.WinDLL("user32", use_last_error=True)
    u32.CreateDesktopW.restype = HANDLE
    # Con permiso para el usuario, el sistema y el contenedor (si no, user32 no arranca en él).
    sd = ctypes.c_void_p()
    sddl = f"D:(A;;GA;;;{user_sid()})(A;;GA;;;SY)(A;;GA;;;{sid_text})"
    _check(
        adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(sd), None),
        "SDDL",
    )
    sa = SECURITY_ATTRIBUTES(ctypes.sizeof(SECURITY_ATTRIBUTES), sd, False)
    hdesk = u32.CreateDesktopW(DESKTOP, None, None, 0, 0x10000000, ctypes.byref(sa))
    _check(hdesk, "CreateDesktop")
    # Para la baja integridad: su carpeta con etiqueta baja (si no, no puede escribir en ella).
    icacls(str(own), "/setintegritylevel", "(OI)(CI)low")

    env = {
        "SYSTEMROOT": os.environ["SYSTEMROOT"],
        "WINDIR": os.environ["WINDIR"],
        # CreateProcess las cambia por las carpetas del contenedor; sin ellas falla (error 203).
        "LOCALAPPDATA": os.environ["LOCALAPPDATA"],
        "USERPROFILE": os.environ["USERPROFILE"],
        "TEMP": str(own / "tmp"),
        "TMP": str(own / "tmp"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    cfg = {
        "secret": str(user / "secreto.txt"),
        "outside": str(user / "escrito.txt"),
        "own": str(own),
        "documents": str(Path.home() / "Documents"),
        "port": port,
    }
    results: dict[str, dict[str, Any]] = {}
    granted = False
    for mode in MODES:
        (user / "escrito.txt").unlink(missing_ok=True)
        container = sid if mode.startswith(("appcontainer", "lpac")) else None
        lpac = mode.startswith("lpac")
        desktop = DESKTOP if mode.endswith("escritorio") else None
        if container is not None and not granted:
            # Lo mínimo para el contenedor: leer el Python y escribir en su carpeta. Después de
            # la baja integridad: con este permiso en la carpeta, el Python a baja integridad no
            # carga sus DLL (0xC0000135; medido).
            icacls(str(python_dir), "/grant", f"*{sid_text}:(OI)(CI)RX")
            icacls(str(own), "/grant", f"*{sid_text}:(OI)(CI)M")
            granted = True
        argv = [str(python), "-I", "-X", "utf8", str(own / "sonda.py"), json.dumps(cfg)]
        code, lines, _, peak, _ = launch(mode, argv, own, env, True, container, desktop, lpac)
        probes = json.loads(lines[-1]) if lines and lines[-1].startswith("{") else {}
        # Arranque: 7 veces «print» y salir, con los límites puestos.
        starts = []
        for _ in range(7):
            argv = [str(python), "-I", "-c", "print('ready')"]
            _, _, first, _, _ = launch(mode, argv, own, env, True, container, desktop, lpac)
            if first is not None:
                starts.append(first)
        results[mode] = {
            "code": code,
            "probes": probes,
            "raw": lines[:-1] if probes else lines,
            "peak_mb": round(peak / 2**20, 1),
            "start_ms": round(statistics.median(starts) * 1000) if starts else None,
        }
        with contextlib.suppress(OSError):
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\NyxSondaExtensiones")
    server.close()
    u32.CloseDesktop(HANDLE(hdesk))
    icacls(str(python_dir), "/remove", f"*{sid_text}")
    delete_appcontainer()

    text = mask(render(results, python_dir))
    print(text)
    if report:
        report.write_text(text, encoding="utf-8", newline="\n")


LABELS = {
    "modulos": "Python funciona (ssl, sqlite3, ctypes, asyncio)",
    "leer_archivo_usuario": "Leer un archivo del usuario",
    "listar_documentos": "Ver qué hay en Documentos",
    "escribir_fuera": "Escribir fuera de su carpeta",
    "escribir_su_carpeta": "Escribir en su carpeta",
    "red_internet": "Conectar a internet (1.1.1.1:443)",
    "dns": "Resolver nombres (DNS)",
    "red_este_pc": "Conectar a un servidor del propio PC",
    "registro_leer": "Leer el registro del usuario",
    "registro_recientes": "Ver la lista de documentos recientes (registro)",
    "registro_escribir": "Escribir en el registro del usuario",
    "lanzar_proceso": "Lanzar otro programa (cmd)",
    "portapapeles": "Abrir el portapapeles",
    "pantalla": "Copiar la pantalla",
    "titulo_ventana_activa": "Leer el título de la ventana activa",
    "variables_de_entorno": "Variables de entorno que ve",
    "memoria_512MB": "Reservar 512 MB (límite 256 MB)",
    "cpu_un_hilo_2s": f"CPU de un hilo en 2 s (tope {CPU_RATE_PERCENT} % del equipo)",
}


def render(results: dict[str, dict[str, Any]], python_dir: Path) -> str:
    modes = MODES
    head = (
        "Sin aislar", "Baja integridad", "AppContainer", "AppContainer + escritorio aparte",
        "LPAC + escritorio aparte",
    )  # fmt: skip
    out = [
        "# Aislamiento de extensiones con código (7.05)",
        "",
        f"Generado con `scripts/sandbox_probe.py` el {time.strftime('%Y-%m-%d')} en Windows "
        f"{platform.version()}, {os.cpu_count()} hilos. Python embeddable oficial "
        f"{python_version(python_dir)}. Todas las formas, dentro de un objeto de trabajo con: "
        f"memoria {MEMORY_LIMIT // 2**20} MB, 1 proceso, prioridad por debajo de lo normal, "
        f"CPU {CPU_RATE_PERCENT} % del equipo (tope duro) y todas las restricciones de interfaz.",
        "",
        "| Prueba | " + " | ".join(head) + " |",
        "| --- | " + " | ".join("---" for _ in modes) + " |",
    ]
    for key, label in LABELS.items():
        cells = []
        for m in modes:
            got = results[m]["probes"].get(key)
            if got is None:
                cells.append("—")
            elif got[0] == "permitido":
                cells.append(f"**sí** ({got[1]})")
            else:
                cells.append(f"no ({got[1]})")
        out.append(f"| {label} | " + " | ".join(c.replace("|", "/") for c in cells) + " |")
    out.append(
        "| Arranque hasta la 1.ª línea (mediana de 7) | "
        + " | ".join(f"{results[m]['start_ms']} ms" for m in modes)
        + " |"
    )
    out.append(
        "| Código de salida | " + " | ".join(f"{results[m]['code']:#x}" for m in modes) + " |"
    )
    out.append(
        "| Pico de memoria de la sonda | "
        + " | ".join(f"{results[m]['peak_mb']} MB" for m in modes)
        + " |"
    )
    for m in modes:
        if results[m]["raw"]:
            out += ["", f"Salida suelta ({m}):", "", "```text", *results[m]["raw"][:20], "```"]
    return "\n".join(out) + "\n"


def python_version(python_dir: Path) -> str:
    out = subprocess.run(
        [
            str(python_dir / "python.exe"),
            "-I",
            "-c",
            "import platform; print(platform.python_version())",
        ],
        capture_output=True,
        text=True,
    )
    return out.stdout.strip() or "?"


def mask(text: str) -> str:
    """El informe va al repositorio: sin la carpeta ni el nombre del usuario."""
    home = str(Path.home())
    for variant in (home.replace("\\", "\\\\"), home):
        text = text.replace(variant, "%USERPROFILE%")
    user = os.environ.get("USERNAME", "")
    return text.replace(user, "<usuario>") if user else text


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--trabajo", type=Path, required=True)
    parser.add_argument("--informe", type=Path)
    args = parser.parse_args()
    if sys.platform != "win32":
        sys.exit("Solo Windows")
    run(args.python.resolve(), args.trabajo.resolve(), args.informe)


if __name__ == "__main__":
    main()
