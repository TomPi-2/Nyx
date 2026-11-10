"""Ventanas y monitores con Win32: listar, encontrar por nombre, activar y colocar."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
from dataclasses import dataclass
from functools import lru_cache

from rapidfuzz import fuzz

from nyx.index.aliases import normalize

log = logging.getLogger(__name__)

Rect = tuple[int, int, int, int]  # izquierda, arriba, derecha, abajo

# Ventanas propias de Nyx y del sistema que nunca son «la ventana» del usuario.
_IGNORED_PROCESSES = {
    "nyx-ui.exe",
    "textinputhost.exe",
    "searchhost.exe",
    "startmenuexperiencehost.exe",
}
_IGNORED_TITLES = {"Program Manager", "Nyx"}
_DWMWA_CLOAKED = 14
_DWMWA_EXTENDED_FRAME_BOUNDS = 9


@dataclass(frozen=True, slots=True)
class Window:
    hwnd: int
    title: str
    process: str  # ejecutable en minúsculas


@dataclass(frozen=True, slots=True)
class Monitor:
    rect: Rect
    work: Rect  # sin la barra de tareas
    primary: bool


def _rect(values: tuple[int, ...] | list[int]) -> Rect:
    left, top, right, bottom = values
    return (int(left), int(top), int(right), int(bottom))


@lru_cache(maxsize=256)
def _process_name(pid: int) -> str:
    import psutil

    try:
        return str(psutil.Process(pid).name()).lower()
    except Exception:
        return ""


def _cloaked(hwnd: int) -> bool:
    """Ventanas «ocultas» por DWM (apps de la Store suspendidas, otros escritorios)."""
    value = ctypes.c_int(0)
    ctypes.windll.dwmapi.DwmGetWindowAttribute(
        ctypes.c_void_p(hwnd), _DWMWA_CLOAKED, ctypes.byref(value), ctypes.sizeof(value)
    )
    return value.value != 0


def list_windows() -> list[Window]:
    """Ventanas de nivel superior visibles para el usuario, de la más reciente a la más antigua."""
    import win32con
    import win32gui
    import win32process

    found: list[Window] = []

    def visit(hwnd: int, _: object) -> bool:
        if not win32gui.IsWindowVisible(hwnd) or win32gui.GetWindow(hwnd, win32con.GW_OWNER):
            return True
        title = win32gui.GetWindowText(hwnd)
        if not title or title in _IGNORED_TITLES:
            return True
        ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        if ex & win32con.WS_EX_TOOLWINDOW or _cloaked(hwnd):
            return True
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        process = _process_name(pid)
        if process in _IGNORED_PROCESSES:
            return True
        found.append(Window(hwnd, title, process))
        return True

    win32gui.EnumWindows(visit, None)
    return found


def foreground() -> Window | None:
    import win32gui

    hwnd = win32gui.GetForegroundWindow()
    return next((w for w in list_windows() if w.hwnd == hwnd), None)


def find_windows(
    name: str, process: str | None = None, windows: list[Window] | None = None
) -> list[Window]:
    """Ventanas que encajan con `name` (título) o con el ejecutable `process`."""
    windows = list_windows() if windows is None else windows
    query = normalize(name)
    scored: list[tuple[float, int, Window]] = []
    for order, w in enumerate(windows):
        if process and w.process == process:
            score = 100.0
        else:
            title = normalize(w.title)
            exe = w.process.removesuffix(".exe")
            score = max(
                float(fuzz.partial_ratio(query, title)) if len(query) >= 3 else 0.0,
                float(fuzz.ratio(query, exe)),
            )
        if score >= 80:
            scored.append((score, -order, w))
    return [w for _, _, w in sorted(scored, key=lambda t: (t[0], t[1]), reverse=True)]


def activate(hwnd: int) -> bool:
    """Trae la ventana al frente.

    Windows solo deja cambiar la ventana activa al proceso que recibió la última entrada.
    1. Un movimiento de ratón de 0 píxeles cuenta como entrada y no se nota. (El truco
       habitual de pulsar Alt deja la barra de menús activada en la ventana nueva.)
    2. Si no basta, se comparte la entrada con la ventana activa (AttachThreadInput).
    """
    import win32api
    import win32con
    import win32gui
    import win32process

    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, 0, 0, 0, 0)
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        log.debug("SetForegroundWindow falló al primer intento", exc_info=True)
    if win32gui.GetForegroundWindow() == hwnd:
        return True
    current = win32gui.GetForegroundWindow()
    fg_thread = win32process.GetWindowThreadProcessId(current)[0] if current else 0
    own_thread = win32api.GetCurrentThreadId()
    attached = bool(fg_thread) and fg_thread != own_thread
    try:
        if attached:
            win32process.AttachThreadInput(own_thread, fg_thread, True)
        win32gui.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        log.debug("SetForegroundWindow falló", exc_info=True)
    finally:
        if attached:
            win32process.AttachThreadInput(own_thread, fg_thread, False)
    return bool(win32gui.GetForegroundWindow() == hwnd)


def show(hwnd: int, how: str) -> None:
    import win32con
    import win32gui

    cmd = {
        "maximize": win32con.SW_MAXIMIZE,
        "minimize": win32con.SW_MINIMIZE,
        "restore": win32con.SW_RESTORE,
    }[how]
    win32gui.ShowWindow(hwnd, cmd)


def monitors() -> list[Monitor]:
    import win32api

    out = []
    for handle, _, _ in win32api.EnumDisplayMonitors():
        info = win32api.GetMonitorInfo(int(handle))
        out.append(Monitor(_rect(info["Monitor"]), _rect(info["Work"]), bool(info["Flags"] & 1)))
    return sorted(out, key=lambda m: (m.rect[0], m.rect[1]))


def monitor_of(rect: Rect, screens: list[Monitor]) -> int:
    """Índice del monitor que contiene el centro del rectángulo."""
    cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    for i, m in enumerate(screens):
        if m.rect[0] <= cx < m.rect[2] and m.rect[1] <= cy < m.rect[3]:
            return i
    return 0


def half(work: Rect, side: str) -> Rect:
    left, top, right, bottom = work
    mid = (left + right) // 2
    return (left, top, mid, bottom) if side == "left" else (mid, top, right, bottom)


def translate(rect: Rect, src: Rect, dst: Rect) -> Rect:
    """Mismo sitio relativo y tamaño proporcional en otro monitor (área de trabajo)."""
    sw, sh = src[2] - src[0], src[3] - src[1]
    dw, dh = dst[2] - dst[0], dst[3] - dst[1]
    fx, fy = dw / sw, dh / sh
    left = dst[0] + round((rect[0] - src[0]) * fx)
    top = dst[1] + round((rect[1] - src[1]) * fy)
    width = min(dw, round((rect[2] - rect[0]) * fx))
    height = min(dh, round((rect[3] - rect[1]) * fy))
    return (left, top, left + width, top + height)


def window_rect(hwnd: int) -> Rect:
    import win32gui

    return _rect(win32gui.GetWindowRect(hwnd))


def place(hwnd: int, target: Rect) -> None:
    """Coloca la ventana en `target` compensando los bordes invisibles de Windows 10/11."""
    import win32con
    import win32gui

    if win32gui.GetWindowPlacement(hwnd)[1] == win32con.SW_SHOWMAXIMIZED:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    outer = window_rect(hwnd)
    frame = ctypes.wintypes.RECT()
    ctypes.windll.dwmapi.DwmGetWindowAttribute(
        ctypes.c_void_p(hwnd),
        _DWMWA_EXTENDED_FRAME_BOUNDS,
        ctypes.byref(frame),
        ctypes.sizeof(frame),
    )
    dl, dt = frame.left - outer[0], frame.top - outer[1]
    dr, db = outer[2] - frame.right, outer[3] - frame.bottom
    left, top, right, bottom = target[0] - dl, target[1] - dt, target[2] + dr, target[3] + db
    win32gui.SetWindowPos(
        hwnd,
        0,
        left,
        top,
        right - left,
        bottom - top,
        win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE,
    )


def is_maximized(hwnd: int) -> bool:
    import win32con
    import win32gui

    return bool(win32gui.GetWindowPlacement(hwnd)[1] == win32con.SW_SHOWMAXIMIZED)


def close_window(hwnd: int) -> None:
    """Pide a la ventana que se cierre (como pulsar la X): la app puede preguntar si guardar.
    Nunca se mata el proceso."""
    import win32con
    import win32gui

    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)


def monitor_device(hwnd: int) -> str:
    """Monitor donde está una ventana, por su nombre de dispositivo («\\.\\DISPLAY2»), el
    mismo que usa la interfaz para elegir monitor. "" si no se puede saber."""
    try:
        import win32api
        import win32con

        monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
        return str(win32api.GetMonitorInfo(monitor).get("Device", ""))
    except Exception:
        log.debug("No se pudo saber el monitor de la ventana %s", hwnd, exc_info=True)
        return ""
