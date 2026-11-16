"""Reglas de leer lo seleccionado y documentos (8.05).

«Resume lo que tengo seleccionado», «tradúceme lo seleccionado al inglés», «¿qué dice esto que
he marcado?», «resume el PDF de Descargas», «resume el último Word», «resume el documento del
contrato», «resume las páginas 5 a 10 del PDF del informe». La herramienta lee y el modelo
resume, traduce o contesta (la frase entera le llega con lo leído).
"""

from __future__ import annotations

import re

from nyx.brain.router.comun import Route, _call, _original, rule
from nyx.index.service import SystemIndex

_DO = (
    r"(?:resume(?:me)?|traduce(?:me)?(?:\s+al\s+[a-z]+)?|explica(?:me)?|lee(?:me)?|"
    r"corrige(?:me)?|que\s+(?:dice|pone|significa)|de\s+que\s+(?:va|trata)|"
    r"haz(?:me)?\s+un\s+resumen\s+(?:de|del(?=\s)))"
)
# «el documento de Word», «el PDF», «el documento»
_KIND = (
    r"(?:documento\s+(?:de\s+)?(?=pdf|word))?(?P<kind>pdf|word|documento|archivo\s+de\s+texto|txt)"
)
_FOLDER = r"(?P<folder>descargas|documentos|escritorio)"
_KINDS = {"pdf": "pdf", "word": "word", "txt": "text", "archivo de texto": "text"}


@rule(
    "read_selection",
    # «resume lo que tengo seleccionado», «explícame qué significa el párrafo que he subrayado»
    rf"^{_DO}\s+(?:.{{1,60}}?\s+)?(?:que\s+(?:tengo|he|has)\s+)?"
    r"(?:seleccionad|marcad|subrayad|resaltad)[oa]s?(?:\s+al\s+[a-z]+)?$",
)
def _read_selection(_: re.Match[str], __: SystemIndex) -> Route:
    return _call("read_selection", "read_text", source="selection")


@rule(
    "read_document",
    # «resume el PDF de Descargas», «resume el último Word», «¿de qué va el PDF del contrato?»
    rf"^{_DO}\s+(?:(?:el|la|este|mi)\s+)?(?:ultimo\s+)?{_KIND}"
    rf"(?:\s+(?:del?|sobre(?:\s+el|\s+la)?|llamado)\s+(?!descargas|documentos|escritorio)(?P<name>.+?))?"
    rf"(?:\s+(?:de|del|que\s+(?:hay|tengo)\s+en)\s+(?:el\s+|la\s+carpeta\s+(?:de\s+)?)?{_FOLDER})?$"
    # «resume las páginas 5 a 10 del PDF del informe»
    rf"|^{_DO}\s+(?:la|las)\s+paginas?\s+(?P<pages>\d{{1,4}}(?:\s+(?:a|al|hasta)\s+\d{{1,4}})?)"
    rf"\s+del\s+(?:pdf|documento)(?:\s+(?:del?|llamado)\s+(?P<name2>.+?))?$",
)
def _read_document(m: re.Match[str], _: SystemIndex) -> Route:
    kind = _KINDS.get(m.group("kind") or "")
    if m.group("pages"):
        kind = "pdf"
    name = m.group("name") or m.group("name2")
    return _call(
        "read_document",
        "read_text",
        source="document",
        file=_original(name) if name else None,
        folder=m.group("folder"),
        kind=kind,
        pages=m.group("pages"),
    )
