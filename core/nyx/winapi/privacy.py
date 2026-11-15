r"""Qué programas usan o han usado el micrófono y la cámara (tarea 8.07). Solo lectura.

Windows lo apunta por usuario en
`HKCU\Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\<cap>`:
una subclave por app de la Tienda (su nombre de paquete) y, en `NonPackaged`, una por programa
(su ruta con `#` en vez de `\`). Cada una con `LastUsedTimeStart` y `LastUsedTimeStop` (FILETIME):
si empezó y no ha parado (`Stop` = 0), lo está usando ahora.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import PureWindowsPath
from typing import Any, Literal

log = logging.getLogger(__name__)

Capability = Literal["microphone", "webcam"]
_BASE = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore"
_EPOCH = datetime(1601, 1, 1)
# Lo que es Nyx (su Python, su app o el de las extensiones): se dice «yo».
_NYX_HINTS = (
    "\\tepnyxnyx\\",  # Nyx instalada (su Python y su app)
    "\\nyx\\core\\",  # Nyx en desarrollo (el Python de su entorno)
    "nyx-ui.exe",
    "\\nyx\\ext-runtime\\",  # el Python de las extensiones
)


@dataclass(frozen=True, slots=True)
class Use:
    name: str  # lo que se dice: «Discord», «WhatsApp»
    in_use: bool
    last: datetime | None  # cuándo empezó (en uso) o cuándo dejó de usarlo
    is_nyx: bool = False


def _filetime(value: object) -> datetime | None:
    if not isinstance(value, int) or value <= 0:
        return None
    return _EPOCH + timedelta(microseconds=value // 10)


def _local(moment: datetime | None) -> datetime | None:
    """FILETIME es UTC: a la hora del PC."""
    if moment is None:
        return None
    from datetime import UTC

    return moment.replace(tzinfo=UTC).astimezone().replace(tzinfo=None)


def _package_name(key: str) -> str:
    """«5319275A.WhatsAppDesktop_cv1g1gvanyjgm» → «WhatsApp Desktop». Partir por mayúsculas
    rompe nombres («Whats App»): solo se separan unas pocas palabras del final."""
    base = key.split("_", 1)[0].split(".")[-1]
    if base in _KNOWN_PACKAGES:
        return _KNOWN_PACKAGES[base]
    for suffix in ("Desktop", "Beta", "Preview", "Insider"):
        if base.endswith(suffix) and len(base) > len(suffix):
            return f"{base[: -len(suffix)]} {suffix}"
    return base or key


_KNOWN_PACKAGES = {
    "WindowsCamera": "Cámara de Windows",
    "WindowsSoundRecorder": "Grabadora de sonido",
    "WindowsFeedbackHub": "Centro de opiniones",
    "Win32WebViewHost": "Windows",
}


def _program_name(path: str) -> str:
    """El nombre del programa: su descripción si la tiene («Discord»), o el del archivo."""
    exe = PureWindowsPath(path)
    try:
        import win32api

        version_info: Any = win32api.GetFileVersionInfo  # sus tipos no conocen estas rutas
        info = version_info(str(exe), "\\VarFileInfo\\Translation")
        lang, codepage = info[0]
        desc = version_info(
            str(exe), f"\\StringFileInfo\\{lang:04x}{codepage:04x}\\FileDescription"
        )
        if isinstance(desc, str) and desc.strip():
            return desc.strip()
    except Exception:  # sin información de versión, o el archivo ya no está
        pass
    return exe.stem[:1].upper() + exe.stem[1:]


def uses(capability: Capability) -> list[Use]:
    """Quién ha usado `capability`, lo que está en uso primero y luego lo más reciente."""
    if sys.platform != "win32":
        return []
    import winreg

    out: list[Use] = []

    def read(key: winreg.HKEYType, name: str, display: str, path: str = "") -> None:
        try:
            start, _ = winreg.QueryValueEx(key, "LastUsedTimeStart")
            stop, _ = winreg.QueryValueEx(key, "LastUsedTimeStop")
        except OSError:
            return  # nunca lo ha usado
        began, ended = _filetime(start), _filetime(stop)
        if began is None:
            return
        in_use = ended is None
        low = path.lower()
        out.append(
            Use(
                display,
                in_use,
                _local(began if in_use else ended),
                is_nyx=any(h in low for h in _NYX_HINTS),
            )
        )

    try:
        root = winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"{_BASE}\\{capability}")
    except OSError:
        return []
    with root:
        for i in range(10_000):
            try:
                sub = winreg.EnumKey(root, i)
            except OSError:
                break
            if sub == "NonPackaged":
                continue
            with winreg.OpenKey(root, sub) as key:
                read(key, sub, _package_name(sub))
        try:
            programs = winreg.OpenKey(root, "NonPackaged")
        except OSError:
            programs = None
        if programs is not None:
            with programs:
                for i in range(10_000):
                    try:
                        sub = winreg.EnumKey(programs, i)
                    except OSError:
                        break
                    path = sub.replace("#", "\\")
                    with winreg.OpenKey(programs, sub) as key:
                        read(key, sub, _program_name(path), path)
    out.sort(key=lambda u: (not u.in_use, -(u.last.timestamp() if u.last else 0)))
    # Un nombre una vez (varias versiones del mismo programa): lo más relevante, que va antes.
    seen: set[str] = set()
    unique = []
    for use in out:
        if use.name.lower() not in seen:
            seen.add(use.name.lower())
            unique.append(use)
    return unique
