"""Reglas de documentos recientes (8.06): «abre el último Word», «¿qué documentos he abierto?».

Van antes de las de archivos: «el último Word» es el último que abriste, no el último que hay
en una carpeta (eso es «el último archivo de Descargas», que sigue en archivos.py).
"""

from __future__ import annotations

import re

from nyx.brain.router.comun import Route, _call, rule
from nyx.index.service import SystemIndex

_KINDS = {
    "word": "word",
    "documento de word": "word",
    "excel": "excel",
    "powerpoint": "powerpoint",
    "power point": "powerpoint",
    "pdf": "pdf",
    "documento": "any",
    "archivo": "any",
}
_KINDS_RE = r"documento de word|power point|word|excel|powerpoint|pdf|documento|archivo"
_KIND = rf"(?P<k>{_KINDS_RE})"
# «que he abierto», «que abrí ayer», «que estaba usando antes»
_THAT = (
    r"que\s+(?:he\s+abierto|abri|estaba\s+(?:editando|usando|mirando)|he\s+estado\s+"
    r"(?:editando|usando))(?:\s+(?:antes|ayer|hoy|hace\s+un\s+rato))?"
)


@rule(
    "recent_open",
    r"^(?:abre|abreme|vuelve\s+a\s+abrir(?:me)?|reabre)\s+(?:otra\s+vez\s+|de\s+nuevo\s+)?"
    rf"(?:el\s+)?(?:ultimo\s+(?P<k>{_KINDS_RE})(?:\s+{_THAT})?|(?P<k2>{_KINDS_RE})\s+{_THAT})$",
)
def _recent_open(m: re.Match[str], _: SystemIndex) -> Route | None:
    kind = _KINDS[m.group("k") or m.group("k2")]
    return _call("recent_open", "recent_files", action="open", kind=kind)


@rule(
    "recent_list",
    r"^(?:que|cuales)\s+(?P<k>documentos|archivos|words|excels|pdfs)\s+(?:he\s+abierto|abri)"
    r"(?:\s+(?:hoy|ultimamente|hace\s+poco|antes))?$",
)
def _recent_list(m: re.Match[str], _: SystemIndex) -> Route | None:
    word = m.group("k")
    kind = {"words": "word", "excels": "excel", "pdfs": "pdf"}.get(word, "any")
    return _call("recent_list", "recent_files", action="list", kind=kind)


@rule(
    "recent_last",
    rf"^cual\s+(?:fue|es)\s+el\s+ultimo\s+{_KIND}\s+que\s+(?:abri|he\s+abierto)$"
    rf"|^como\s+se\s+llama(?:ba)?\s+el\s+(?P<k2>{_KINDS_RE})\s+{_THAT}$",
)
def _recent_last(m: re.Match[str], _: SystemIndex) -> Route | None:
    kind = _KINDS[m.group("k") or m.group("k2")]
    return _call("recent_last", "recent_files", action="list", kind=kind, count=1)
