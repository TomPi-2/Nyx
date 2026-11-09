r"""¿Es un juego la ventana? Nyx nunca pulsa teclas ni hace nada dentro de un juego.

Un ejecutable cuenta como juego si está en una carpeta de juegos de las tiendas (Steam, Riot
salvo su cliente, Epic, EA, Ubisoft, GOG, Xbox) o si la caché lo tiene como juego.
"""

from __future__ import annotations

import re

# Rutas en minúsculas con «\» (se comparan con la ruta del ejecutable).
_GAME_DIRS = re.compile(
    r"\\steamapps\\common\\"
    r"|\\riot games\\(?!riot client\\)"
    r"|\\epic games\\(?!launcher\\)"
    r"|\\ea games\\"
    r"|\\ubisoft game launcher\\games\\"
    r"|\\gog galaxy\\games\\|\\gog games\\"
    r"|\\xboxgames\\"
    r"|\\battle\.net\\(?!battle\.net)"
)


def is_game_exe(path: str) -> bool:
    return bool(_GAME_DIRS.search(path.replace("/", "\\").lower()))


def exe_of_window(hwnd: int) -> str:
    import psutil
    import win32process

    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return str(psutil.Process(pid).exe())
    except Exception:
        return ""


def window_is_game(hwnd: int, process: str, game_processes: set[str]) -> bool:
    """`game_processes`: ejecutables que la caché tiene como juegos."""
    if process and process in game_processes:
        return True
    return is_game_exe(exe_of_window(hwnd))
