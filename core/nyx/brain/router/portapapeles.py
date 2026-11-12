"""Reglas del portapapeles."""

from __future__ import annotations

import re

from nyx.brain.router.comun import (
    _RAW_EXACT,
    _RAW_POLITE,
    Route,
    _call,
    _clean_dictated,
    _original,
    rule,
)
from nyx.index.service import SystemIndex

# --- portapapeles y dictado (6.10) ---


@rule(
    "clipboard_read",
    r"^(?:(?:dime|mirame|ensename|lee(?:me)?)\s+)?(?:"
    r"que\s+(?:tengo|hay|he)\s+copiado(?:\s+en\s+el\s+portapapeles)?|"
    r"que\s+(?:tengo|hay)\s+en\s+el\s+portapapeles|"
    r"(?:el\s+)?portapapeles|"
    r"lo\s+(?:que\s+(?:tengo|hay|he)\s+)?copiado"
    r")$"
    r"|^(?:traduce(?:me)?(?:\s+al\s+[a-z]+)?|resume(?:me)?|corrige(?:me)?(?:\s+la\s+ortografia\s+de)?|explica(?:me)?)\s+"
    r"(?:lo\s+(?:que\s+(?:tengo|hay|he)\s+)?copiado|(?:lo\s+del\s+|el\s+)?portapapeles)(?:\s+al\s+[a-z]+)?$",
)
def _clipboard_read(_: re.Match[str], __: SystemIndex) -> Route:
    return _call("clipboard_read", "clipboard", action="read")


_COPY_PREFIX = re.compile(
    r"^(?:(?:mi|el|la|este|esta)\s+)?(?:correo(?:\s+electr[oó]nico)?|e-?mail|"
    r"texto|frase|enlace|link|url|direcci[oó]n(?:\s+de\s+correo)?|n[uú]mero|c[oó]digo|dato)"
    r"(?:\s*[:\s]\s*)(.+)$",
    re.I,
)


def _raw_without_polite() -> str:
    return _RAW_POLITE.sub("", _clean_dictated(_RAW_EXACT.get())).strip()


@rule(
    "clipboard_write",
    r"^(?:copia(?:me)?|guarda(?:me)?|pon(?:me)?)\s+(?:en\s+el\s+|al\s+)portapapeles\s+(?P<t1>.+)$"
    r"|^copia(?:me)?\s+(?P<t2>.+?)\s+(?:en\s+el\s+|al\s+)portapapeles$",
)
def _clipboard_write(m: re.Match[str], __: SystemIndex) -> Route:
    raw_line = _raw_without_polite()
    extracted: str | None = None
    if m.group("t1"):
        if rm := re.search(
            r"(?:copia(?:me)?|guarda(?:me)?|pon(?:me)?)\s+(?:en\s+el\s+|al\s+)portapapeles[:\s]+(.+)$",
            raw_line,
            re.I,
        ):
            extracted = rm.group(1)
    elif rm := re.match(
        r"^copia(?:me)?\s+(.+?)\s+(?:en\s+el\s+|al\s+)portapapeles$",
        raw_line,
        re.I,
    ):
        extracted = rm.group(1)
    text = (extracted or _original(m.group("t1") or m.group("t2"))).strip()
    if pm := _COPY_PREFIX.match(text):
        text = pm.group(1).strip()
    text = text.strip(" «»\"'")
    return _call("clipboard_write", "clipboard", action="write", text=text)
