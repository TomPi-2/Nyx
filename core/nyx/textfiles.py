"""El texto de un documento para resumirlo o contestar sobre él (tarea 8.05).

PDF con `pypdf` (BSD-3), Word (`.docx`) leyendo su XML con la biblioteca estándar (sin otra
dependencia) y texto plano. Solo se lee: nada se abre ni se ejecuta (macros, enlaces). Lo leído
es contenido de fuera: llega al modelo marcado como información, nunca como órdenes.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

#: Lo que llega al modelo de una vez (como una web de la búsqueda, 6.06).
MAX_CHARS = 6000
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_XML_BYTES = 20 * 1024 * 1024
MAX_PAGES_READ = 40
TEXT_SUFFIXES = frozenset({".txt", ".md", ".csv", ".log", ".json", ".ini"})
SUFFIXES = frozenset({".pdf", ".docx"}) | TEXT_SUFFIXES
KINDS: dict[str, frozenset[str]] = {
    "pdf": frozenset({".pdf"}),
    "word": frozenset({".docx"}),
    "text": TEXT_SUFFIXES,
}
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class DocumentError(ValueError):
    """No se puede leer (el mensaje es para el usuario)."""


@dataclass(frozen=True, slots=True)
class Document:
    text: str
    #: Lo que se ha leído si no es todo («las páginas 1 a 12 de 40», «el principio»).
    partial: str = ""
    pages: int | None = None


def parse_pages(spec: str | None) -> tuple[int, int] | None:
    """«5-10», «5 a 10», «7» → (5, 10), (7, 7)."""
    if not spec:
        return None
    m = re.fullmatch(r"\s*(\d{1,4})\s*(?:(?:-|a|al|hasta)\s*(\d{1,4}))?\s*", spec)
    if m is None:
        raise DocumentError("no entiendo esas páginas")
    first = int(m.group(1))
    last = int(m.group(2) or first)
    if first < 1 or last < first:
        raise DocumentError("no entiendo esas páginas")
    return first, last


def _clip(text: str) -> tuple[str, bool]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    if len(text) <= MAX_CHARS:
        return text, False
    cut = text[:MAX_CHARS]
    # Sin cortar a media frase si se puede.
    end = max(cut.rfind(". "), cut.rfind("\n"))
    return (cut[: end + 1] if end > MAX_CHARS // 2 else cut).strip(), True


def _pdf(path: Path, pages: tuple[int, int] | None) -> Document:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(path)
        if reader.is_encrypted and not reader.decrypt(""):
            raise DocumentError("tiene contraseña")
        total = len(reader.pages)
        first, last = pages or (1, total)
        if first > total:
            raise DocumentError(f"solo tiene {total} páginas")
        last = min(last, total, first + MAX_PAGES_READ - 1)
        parts: list[str] = []
        read_to = first - 1
        for i in range(first - 1, last):
            parts.append(reader.pages[i].extract_text() or "")
            read_to = i + 1
            if sum(len(p) for p in parts) > MAX_CHARS:
                break
    except PdfReadError as e:
        raise DocumentError("el PDF está dañado o no se puede leer") from e
    text, clipped = _clip("\n\n".join(parts))
    if not text:
        raise DocumentError("no tiene texto (puede que sean imágenes escaneadas)")
    whole = first == 1 and read_to >= total and not clipped
    partial = "" if whole else f"las páginas {first} a {read_to} de {total}"
    if clipped and read_to == first:
        partial = f"el principio de la página {first} (de {total})"
    return Document(text, partial, total)


def _docx(path: Path) -> Document:
    try:
        with zipfile.ZipFile(path) as zf:
            info = zf.getinfo("word/document.xml")
            if info.file_size > MAX_XML_BYTES:
                raise DocumentError("es demasiado grande")
            root = ElementTree.fromstring(zf.read(info))
    except (KeyError, zipfile.BadZipFile, ElementTree.ParseError) as e:
        raise DocumentError("no es un documento de Word válido (.docx)") from e
    paragraphs = []
    for p in root.iter(f"{_W}p"):
        line = "".join(t.text or "" for t in p.iter(f"{_W}t"))
        if line.strip():
            paragraphs.append(line)
    text, clipped = _clip("\n".join(paragraphs))
    if not text:
        raise DocumentError("está vacío")
    return Document(text, "el principio" if clipped else "")


def _plain(path: Path) -> Document:
    raw = path.read_bytes()[: MAX_CHARS * 4]
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        decoded = raw.decode("cp1252", errors="replace")
    text, clipped = _clip(decoded)
    if not text:
        raise DocumentError("está vacío")
    return Document(text, "el principio" if clipped or path.stat().st_size > len(raw) else "")


def extract(path: Path, pages: tuple[int, int] | None = None) -> Document:
    suffix = path.suffix.lower()
    if suffix not in SUFFIXES:
        raise DocumentError("solo leo PDF, Word (.docx) y texto")
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            raise DocumentError("es demasiado grande (más de 50 MB)")
        if suffix == ".pdf":
            return _pdf(path, pages)
        if suffix == ".docx":
            return _docx(path)
        return _plain(path)
    except OSError as e:
        raise DocumentError("no puedo abrirlo (¿está abierto en otro programa?)") from e
