"""Atajos de teclado: «ctrl+t» → teclas virtuales, y pulsarlos en la ventana activa."""

from __future__ import annotations

import time
from dataclasses import dataclass

MODIFIERS = {
    "ctrl": 0x11,
    "control": 0x11,
    "control izquierdo": 0x11,
    "alt": 0x12,
    "shift": 0x10,
    "mayus": 0x10,
    "mayús": 0x10,
    "win": 0x5B,
    "windows": 0x5B,
}
NAMED = {
    "enter": 0x0D,
    "intro": 0x0D,
    "esc": 0x1B,
    "escape": 0x1B,
    "tab": 0x09,
    "space": 0x20,
    "espacio": 0x20,
    "backspace": 0x08,
    "delete": 0x2E,
    "supr": 0x2E,
    "insert": 0x2D,
    "home": 0x24,
    "inicio": 0x24,
    "end": 0x23,
    "fin": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "plus": 0xBB,
    "+": 0xBB,
    "minus": 0xBD,
    "-": 0xBD,
    "comma": 0xBC,
    "period": 0xBE,
}
# Teclas extendidas (necesitan KEYEVENTF_EXTENDEDKEY).
_EXTENDED = {0x2E, 0x2D, 0x24, 0x23, 0x21, 0x22, 0x25, 0x26, 0x27, 0x28, 0x5B}

# SPEC sección 8: atajos peligrosos bloqueados. Cerrar apps va por close_app (que comprueba
# cambios sin guardar); borrar, por las herramientas de archivos (papelera, deshacer).
BLOCKED = {
    frozenset({"alt", "f4"}): "para cerrar apps usa close_app",
    frozenset({"shift", "delete"}): "borra sin pasar por la papelera",
    frozenset({"delete"}): "borrar va por las herramientas de archivos",
    frozenset({"ctrl", "delete"}): "borrar va por las herramientas de archivos",
    frozenset({"ctrl", "alt", "delete"}): "atajo del sistema",
    frozenset({"ctrl", "shift", "esc"}): "atajo del sistema",
    frozenset({"win", "r"}): "abre Ejecutar",
    frozenset({"win", "x"}): "abre el menú de administración",
    frozenset({"win", "l"}): "bloquea el equipo",
}


@dataclass(frozen=True, slots=True)
class Hotkey:
    names: tuple[str, ...]  # normalizados: («ctrl», «t»)
    codes: tuple[int, ...]

    @property
    def label(self) -> str:
        return "+".join(n.capitalize() if len(n) > 1 else n.upper() for n in self.names)


def parse(text: str) -> Hotkey:
    """«Ctrl+Shift+T» → Hotkey. ValueError si una tecla no se conoce."""
    raw = text.strip().lower().replace(" + ", "+")
    parts = [p.strip() for p in raw.split("+")] if raw != "+" else ["+"]
    if raw.endswith("++"):  # «ctrl++»
        parts = [*parts[:-2], "+"]
    names: list[str] = []
    codes: list[int] = []
    for part in parts:
        if not part:
            raise ValueError(f"atajo mal formado: {text!r}")
        if part in MODIFIERS:
            name, code = (
                {0x11: "ctrl", 0x12: "alt", 0x10: "shift", 0x5B: "win"}[MODIFIERS[part]],
                MODIFIERS[part],
            )
        elif part in NAMED:
            name, code = (
                {"supr": "delete", "intro": "enter", "escape": "esc"}.get(part, part),
                NAMED[part],
            )
        elif len(part) == 1 and part.isalnum() and part.isascii():
            name, code = part, ord(part.upper())
        elif part.startswith("f") and part[1:].isdigit() and 1 <= int(part[1:]) <= 24:
            name, code = part, 0x70 + int(part[1:]) - 1
        else:
            raise ValueError(f"tecla desconocida: {part!r}")
        names.append(name)
        codes.append(code)
    if not codes:
        raise ValueError("atajo vacío")
    return Hotkey(tuple(names), tuple(codes))


def blocked_reason(hotkey: Hotkey) -> str | None:
    return BLOCKED.get(frozenset(hotkey.names))


def press(hotkey: Hotkey) -> None:
    """Pulsa las teclas en orden y las suelta al revés (la ventana activa las recibe)."""
    import win32api
    import win32con

    def event(code: int, up: bool) -> None:
        flags = win32con.KEYEVENTF_EXTENDEDKEY if code in _EXTENDED else 0
        if up:
            flags |= win32con.KEYEVENTF_KEYUP
        win32api.keybd_event(code, 0, flags, 0)

    try:
        for code in hotkey.codes:
            event(code, up=False)
            time.sleep(0.01)
    finally:
        for code in reversed(hotkey.codes):
            event(code, up=True)
