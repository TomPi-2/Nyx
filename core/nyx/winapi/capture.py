"""Capturas de pantalla con mss: un monitor, todos, o la ventana activa. Se guardan en PNG y
se copian al portapapeles (CF_DIB)."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True, slots=True)
class Shot:
    bgra: npt.NDArray[np.uint8]  # alto × ancho × 4
    width: int
    height: int


def grab(region: tuple[int, int, int, int]) -> Shot:
    """`region` = (izquierda, arriba, derecha, abajo) en píxeles de escritorio virtual."""
    import mss

    left, top, right, bottom = region
    with mss.mss() as sct:
        raw = sct.grab({"left": left, "top": top, "width": right - left, "height": bottom - top})
        data = np.frombuffer(raw.bgra, dtype=np.uint8).reshape(raw.height, raw.width, 4).copy()
    data[..., 3] = 255
    return Shot(data, raw.width, raw.height)


def save_png(shot: Shot, path: Path) -> Path:
    import mss.tools

    path.parent.mkdir(parents=True, exist_ok=True)
    rgb = shot.bgra[..., [2, 1, 0]].tobytes()
    mss.tools.to_png(rgb, (shot.width, shot.height), output=str(path))
    return path


def to_dib(shot: Shot) -> bytes:
    """Mapa de bits de 32 bits de abajo arriba, como lo espera el portapapeles."""
    header = struct.pack(
        "<IiiHHIIiiII",
        40,
        shot.width,
        shot.height,
        1,
        32,
        0,
        shot.width * shot.height * 4,
        0,
        0,
        0,
        0,
    )
    return header + shot.bgra[::-1].tobytes()


def copy_to_clipboard(shot: Shot) -> None:
    import win32clipboard

    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()  # type: ignore[no-untyped-call]
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, to_dib(shot))  # type: ignore[no-untyped-call]
    finally:
        win32clipboard.CloseClipboard()  # type: ignore[no-untyped-call]
