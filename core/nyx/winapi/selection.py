"""El texto seleccionado en una ventana (tarea 8.05).

1. **UI Automation**: el control con patrón de texto que tiene algo seleccionado (Word, el Bloc
   de notas, Edge y Chrome, la mayoría de editores). No toca el portapapeles ni el teclado.
2. **Ctrl+C** si UIA no lo ve: solo cuando el portapapeles está vacío o solo tiene texto, que
   se guarda y se devuelve después (una imagen o unos archivos copiados se perderían: entonces
   no se hace). Nunca en terminales (Ctrl+C para lo que se está ejecutando) ni en juegos: eso lo
   comprueba quien llama.
"""

from __future__ import annotations

import logging
import time
from typing import Any

log = logging.getLogger(__name__)

MAX_SELECTION = 20000
_TEXT_PATTERN = 10014
_IS_TEXT_PATTERN_AVAILABLE = 30040
COPY_WAIT_S = 0.6


def uia_selection(hwnd: int) -> str | None:
    """Lo seleccionado en la ventana según UI Automation, o None."""
    import comtypes
    import comtypes.client

    comtypes.CoInitialize()
    try:
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as U

        auto: Any = comtypes.client.CreateObject(U.CUIAutomation, interface=U.IUIAutomation)
        root = auto.ElementFromHandle(hwnd)
        cond = auto.CreatePropertyCondition(_IS_TEXT_PATTERN_AVAILABLE, True)
        found = root.FindAll(U.TreeScope_Subtree, cond)
        for i in range(min(found.Length, 200)):
            try:
                pattern = found.GetElement(i).GetCurrentPattern(_TEXT_PATTERN)
                ranges = pattern.QueryInterface(U.IUIAutomationTextPattern).GetSelection()
                texts = [ranges.GetElement(j).GetText(MAX_SELECTION) for j in range(ranges.Length)]
            except comtypes.COMError, AttributeError, ValueError:
                continue
            text = "\n".join(t for t in texts if t)
            if text.strip():
                return text
        return None
    except Exception as e:  # UIA de una app rara: se prueba lo siguiente
        log.info("UIA no da la selección: %s", e)
        return None
    finally:
        comtypes.CoUninitialize()


def _only_text_in_clipboard() -> bool:
    import win32clipboard
    import win32con

    cb: Any = win32clipboard
    text_formats = {win32con.CF_UNICODETEXT, win32con.CF_TEXT, win32con.CF_OEMTEXT, 16}  # LOCALE
    cb.OpenClipboard()
    try:
        fmt = cb.EnumClipboardFormats(0)
        while fmt:
            if fmt not in text_formats:
                return False
            fmt = cb.EnumClipboardFormats(fmt)
        return True
    finally:
        cb.CloseClipboard()


def copy_selection(hwnd: int) -> str | None:
    """Ctrl+C en la ventana y el portapapeles como estaba. None si no se puede o no copia nada."""
    import win32clipboard

    from nyx.tools.clipboard import read_clipboard_text, write_clipboard_text
    from nyx.winapi import keys, windows

    cb: Any = win32clipboard

    if not _only_text_in_clipboard():
        return None
    saved = read_clipboard_text()
    fg = windows.foreground()
    if (fg is None or fg.hwnd != hwnd) and not windows.activate(hwnd):
        return None
    time.sleep(0.15)
    before = cb.GetClipboardSequenceNumber()
    keys.press(keys.parse("ctrl+c"))
    deadline = time.monotonic() + COPY_WAIT_S
    while time.monotonic() < deadline and cb.GetClipboardSequenceNumber() == before:
        time.sleep(0.03)
    copied = read_clipboard_text() if cb.GetClipboardSequenceNumber() != before else None
    # Lo que había, otra vez en su sitio.
    try:
        if saved is not None:
            write_clipboard_text(saved)
        elif copied is not None:
            cb.OpenClipboard()
            try:
                cb.EmptyClipboard()
            finally:
                cb.CloseClipboard()
    except Exception as e:
        log.warning("No se pudo devolver el portapapeles: %s", e)
    return copied[:MAX_SELECTION] if copied else None
