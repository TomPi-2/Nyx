"""Ventanas ocultas por Nyx (tarea 8.08): fuera de la pantalla, de la barra de tareas y de
Alt+Tab, hasta «enséñalas».

Se ocultan con `ShowWindow(SW_HIDE)` (la app sigue abierta y funcionando) y se apuntan en
`%LOCALAPPDATA%\\Nyx\\ocultas.json` para devolverlas siempre: con «enséñalas», al cerrar Nyx y
al arrancarla (si Nyx se cayó con ventanas ocultas, vuelven). Nunca juegos ni Nyx: eso lo
comprueba la herramienta.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from nyx.paths import local_dir

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class HiddenWindow:
    hwnd: int
    process: str
    title: str


def _show_window(hwnd: int, show: bool) -> bool:
    import win32con
    import win32gui

    if not win32gui.IsWindow(hwnd):
        return False
    win32gui.ShowWindow(hwnd, win32con.SW_SHOWNA if show else win32con.SW_HIDE)
    return True


class HiddenWindows:
    def __init__(
        self, path: Path | None = None, *, show: Callable[[int, bool], bool] = _show_window
    ) -> None:
        self.path = path or local_dir() / "ocultas.json"
        self._show = show
        self._lock = threading.Lock()

    def _load(self) -> list[HiddenWindow]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return [HiddenWindow(int(d["hwnd"]), str(d["process"]), str(d["title"])) for d in data]
        except OSError, ValueError, KeyError, TypeError:
            return []

    def _save(self, items: list[HiddenWindow]) -> None:
        if not items and not self.path.exists():
            return  # nada oculto y nunca lo hubo: ni archivo
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps([asdict(i) for i in items], ensure_ascii=False), "utf-8")
        tmp.replace(self.path)

    def hidden(self) -> list[HiddenWindow]:
        with self._lock:
            return self._load()

    def hide(self, windows: list[HiddenWindow]) -> list[HiddenWindow]:
        """Oculta y apunta (antes de ocultar: si algo falla, se sabe cuáles devolver)."""
        with self._lock:
            current = self._load()
            known = {w.hwnd for w in current}
            fresh = [w for w in windows if w.hwnd not in known]
            self._save(current + fresh)
            done = [w for w in fresh if self._show(w.hwnd, False)]
            if len(done) != len(fresh):
                self._save(current + done)
        return done

    def show(self, process: str | None = None) -> list[HiddenWindow]:
        """Devuelve las de esa app (o todas). Las que ya no existen se olvidan."""
        with self._lock:
            current = self._load()
            back = [w for w in current if process is None or w.process == process]
            for w in back:
                try:
                    self._show(w.hwnd, True)
                except Exception as e:
                    log.warning("No se pudo volver a enseñar %s: %s", w.title, e)
            self._save([w for w in current if w not in back])
        return back
