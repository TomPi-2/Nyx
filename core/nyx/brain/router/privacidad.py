"""Reglas de privacidad (8.07): quién usa el micrófono y la cámara, sin el modelo.

«¿Quién está usando el micro?», «¿alguien me está escuchando?», «¿qué apps han usado la cámara
hoy?». Solo lee el registro de privacidad de Windows (`privacy_check`).
"""

from __future__ import annotations

import re

from nyx.brain.router.comun import Route, _call, rule
from nyx.index.service import SystemIndex

_WHO = r"(?:quien|que\s+(?:app|apps|aplicacion|aplicaciones|programa|programas))"
_DEVICE = r"(?:el\s+|la\s+|mi\s+)?(?P<d>micro|microfono|camara|webcam)"


def _device(word: str | None) -> str:
    if not word:
        return "both"
    return "camera" if word in ("camara", "webcam") else "microphone"


@rule(
    "privacy_now",
    rf"^{_WHO}\s+(?:esta|estan|me\s+esta|me\s+estan)\s+usando\s+{_DEVICE}(?:\s+ahora(?:\s+mismo)?)?$"
    r"|^(?:alguien|algo|alguna\s+app)\s+me\s+esta\s+(?P<e>escuchando|grabando|viendo)$"
    r"|^(?:se\s+)?esta\s+usando\s+(?:el\s+|la\s+|mi\s+)?(?P<d2>micro|microfono|camara|webcam)"
    r"(?:\s+ahora(?:\s+mismo)?)?$",
)
def _privacy_now(m: re.Match[str], _: SystemIndex) -> Route | None:
    seen = m.group("e")
    device = (
        "microphone" if seen == "escuchando" else "camera" if seen == "viendo" else None
    ) or _device(m.group("d") or m.group("d2"))
    return _call("privacy_now", "privacy_check", device=device, when="now")


@rule(
    "privacy_recent",
    rf"^{_WHO}\s+(?:ha|han)\s+usado\s+{_DEVICE}"
    r"(?:\s+(?P<w>hoy|esta\s+semana|ultimamente|estos\s+dias))?$",
)
def _privacy_recent(m: re.Match[str], _: SystemIndex) -> Route | None:
    when = "today" if m.group("w") == "hoy" else "recent"
    return _call("privacy_recent", "privacy_check", device=_device(m.group("d")), when=when)
